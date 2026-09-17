"""Fixed-horizon, terminal-operation shipment accuracy for TwinWorks."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccuracySummaryLog, ForecastLog, PositionState


FORMULA_VERSION = "TW-ACC-1.1"
HORIZONS = (7, 14, 21)
WINDOW_EXTRA_DAYS = 6
MAE_SLA_DAYS = 14.0
HEADLINE_WEIGHTS = {7: 0.20, 14: 0.35, 21: 0.45}
CONFIDENCE_ORDER = {
    "INSUFFICIENT": 0,
    "PRELIMINARY": 1,
    "DEVELOPING": 2,
    "ESTABLISHED": 3,
}


def _canonical(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )


def _hash(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def confidence_tier(n: int) -> str:
    if n < 5:
        return "INSUFFICIENT"
    if n < 12:
        return "PRELIMINARY"
    if n < 25:
        return "DEVELOPING"
    return "ESTABLISHED"


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Return a 95% Wilson score interval as percentages."""
    if n <= 0:
        return 0.0, 0.0
    proportion = successes / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / n + z * z / (4 * n * n)
    ) / denominator
    return round(100 * max(0.0, center - margin), 1), round(
        100 * min(1.0, center + margin), 1)


def _score_errors(errors: list[int], p80_hits: list[bool]) -> dict:
    n = len(errors)
    if n == 0:
        return {
            "n": 0,
            "score": None,
            "confidence": "INSUFFICIENT",
            "mae_days": None,
            "bias_days": None,
            "hit3_pct": None,
            "hit7_pct": None,
            "p80_sample_size": 0,
            "p80_coverage_pct": None,
            "p80_wilson_low_pct": None,
            "p80_wilson_high_pct": None,
        }
    mae = mean(abs(error) for error in errors)
    bias = mean(errors)
    hit3 = 100 * sum(abs(error) <= 3 for error in errors) / n
    hit7 = 100 * sum(abs(error) <= 7 for error in errors) / n
    timing_points = 60 * max(0.0, 1 - mae / MAE_SLA_DAYS)
    hit_points = 25 * hit7 / 100
    bias_points = 15 * max(0.0, 1 - abs(bias) / MAE_SLA_DAYS)
    p80_n = len(p80_hits)
    p80_successes = sum(p80_hits)
    low, high = wilson_interval(p80_successes, p80_n) if p80_n else (None, None)
    return {
        "n": n,
        "score": round(timing_points + hit_points + bias_points),
        "confidence": confidence_tier(n),
        "mae_days": round(mae, 1),
        "bias_days": round(bias, 1),
        "hit3_pct": round(hit3, 1),
        "hit7_pct": round(hit7, 1),
        "p80_sample_size": p80_n,
        "p80_coverage_pct": round(100 * p80_successes / p80_n, 1) if p80_n else None,
        "p80_wilson_low_pct": low,
        "p80_wilson_high_pct": high,
    }


def _headline(horizons: dict[int, dict]) -> dict | None:
    if any((horizons.get(horizon) or {}).get("n", 0) < 5 for horizon in HORIZONS):
        return None
    score = round(sum(
        HEADLINE_WEIGHTS[horizon] * horizons[horizon]["score"]
        for horizon in HORIZONS
    ))
    confidence = min(
        (horizons[horizon]["confidence"] for horizon in HORIZONS),
        key=lambda item: CONFIDENCE_ORDER[item],
    )
    return {"score": score, "confidence": confidence}


def _as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


async def _accuracy_rows(
        db: AsyncSession, programs: list[str], as_of: date) -> tuple[list, list]:
    programs = [program.upper() for program in programs]
    physical = (await db.execute(
        select(PositionState).where(
            PositionState.program.in_(programs),
            PositionState.pack.is_not(None),
            PositionState.pack <= as_of,
            PositionState.source == "ifs-sync",
        )
    )).scalars().all()
    forecasts = (await db.execute(
        select(ForecastLog).where(
            ForecastLog.program.in_(programs),
            ForecastLog.build_date <= as_of.isoformat(),
        ).order_by(
            ForecastLog.program, ForecastLog.so, ForecastLog.build_date, ForecastLog.id)
    )).scalars().all()
    return physical, forecasts


async def compute_accuracy_scores(
        db: AsyncSession, *, programs: list[str], as_of: date | None = None) -> dict:
    """Compute Accuracy v1.1 without mutating the score history."""
    as_of = as_of or date.today()
    program_codes = [program.upper() for program in programs]
    positions, forecasts = await _accuracy_rows(db, program_codes, as_of)
    forecasts_by_unit: dict[tuple[str, str], list[ForecastLog]] = defaultdict(list)
    for forecast in forecasts:
        forecasts_by_unit[(forecast.program, forecast.so)].append(forecast)

    output = {}
    for program in program_codes:
        units = [position for position in positions if position.program == program]
        unit_keys = {(position.program, position.so) for position in units}
        post_ship_records = 0
        cohort_by_horizon: dict[int, list[dict]] = {horizon: [] for horizon in HORIZONS}
        missing_by_horizon = {horizon: 0 for horizon in HORIZONS}
        for unit in units:
            pack = _as_date(unit.pack)
            unit_forecasts = forecasts_by_unit.get((program, unit.so), [])
            post_ship_records += sum(
                _as_date(row.build_date) >= pack for row in unit_forecasts
            )
            for horizon in HORIZONS:
                window_end = pack - timedelta(days=horizon)
                window_start = pack - timedelta(days=horizon + WINDOW_EXTRA_DAYS)
                candidates = [
                    row for row in unit_forecasts
                    if window_start <= _as_date(row.build_date) <= window_end
                    and _as_date(row.build_date) < pack
                    and row.p50_date is not None
                ]
                if not candidates:
                    missing_by_horizon[horizon] += 1
                    continue
                selected = max(
                    candidates,
                    key=lambda row: (_as_date(row.build_date), row.id),
                )
                cohort_by_horizon[horizon].append({
                    "forecast_id": selected.id,
                    "program": program,
                    "serial": unit.serial,
                    "so": unit.so,
                    "build_date": _as_date(selected.build_date),
                    "actual_ship_date": pack,
                    "p50_date": selected.p50_date,
                    "p80_date": selected.p80_date,
                    "error_days": (selected.p50_date - pack).days,
                    "forecast_age_days": (pack - _as_date(selected.build_date)).days,
                    "model_epoch_key": selected.model_epoch_key,
                    "model_status": selected.model_status,
                    "simulation_snapshot_id": selected.simulation_snapshot_id,
                })

        horizons = {}
        for horizon in HORIZONS:
            cohort = cohort_by_horizon[horizon]
            errors = [row["error_days"] for row in cohort]
            p80_hits = [
                row["actual_ship_date"] <= row["p80_date"]
                for row in cohort if row["p80_date"] is not None
            ]
            metrics = _score_errors(errors, p80_hits)
            source_ids = sorted(row["forecast_id"] for row in cohort)
            cohort_payload = [{
                **row,
                "build_date": row["build_date"].isoformat(),
                "actual_ship_date": row["actual_ship_date"].isoformat(),
                "p50_date": row["p50_date"].isoformat(),
                "p80_date": row["p80_date"].isoformat() if row["p80_date"] else None,
            } for row in cohort]
            horizons[horizon] = {
                **metrics,
                "horizon_days": horizon,
                "window_extra_days": WINDOW_EXTRA_DAYS,
                "observed_unit_count": len(units),
                "missing_window_count": missing_by_horizon[horizon],
                "source_forecast_ids": source_ids,
                "cohort_hash": _hash(cohort_payload),
                "cohort": cohort_payload,
            }
        headline = _headline(horizons)
        output[program] = {
            "program": program,
            "formula_version": FORMULA_VERSION,
            "as_of_date": as_of.isoformat(),
            "observed_unit_count": len(units),
            "forecasted_unit_count": len(unit_keys & set(forecasts_by_unit)),
            "post_ship_record_count": post_ship_records,
            "horizons": horizons,
            "headline_score": headline["score"] if headline else None,
            "headline_confidence": headline["confidence"] if headline else "INSUFFICIENT",
        }
    return {
        "formula_version": FORMULA_VERSION,
        "as_of_date": as_of.isoformat(),
        "programs": output,
        "headline_weights": HEADLINE_WEIGHTS,
        "mae_sla_days": MAE_SLA_DAYS,
        "truth": "COMPLETED_TERMINAL_SHIP_OPERATION",
    }


async def capture_accuracy_summaries(
        db: AsyncSession, *, programs: list[str], as_of: date | None = None) -> dict:
    """Append one immutable daily summary per program/horizon when content is new."""
    result = await compute_accuracy_scores(db, programs=programs, as_of=as_of)
    as_of_date = date.fromisoformat(result["as_of_date"])
    created = 0
    rows = []
    for program in programs:
        program_result = result["programs"][program.upper()]
        for horizon in HORIZONS:
            item = program_result["horizons"][horizon]
            record = {
                "as_of_date": as_of_date.isoformat(),
                "program": program.upper(),
                "horizon_days": horizon,
                "formula_version": FORMULA_VERSION,
                "score": item["score"],
                "confidence": item["confidence"],
                "sample_size": item["n"],
                "observed_unit_count": item["observed_unit_count"],
                "missing_window_count": item["missing_window_count"],
                "post_ship_record_count": program_result["post_ship_record_count"],
                "mae_days": item["mae_days"],
                "bias_days": item["bias_days"],
                "hit3_pct": item["hit3_pct"],
                "hit7_pct": item["hit7_pct"],
                "p80_sample_size": item["p80_sample_size"],
                "p80_coverage_pct": item["p80_coverage_pct"],
                "p80_wilson_low_pct": item["p80_wilson_low_pct"],
                "p80_wilson_high_pct": item["p80_wilson_high_pct"],
                "source_forecast_ids": item["source_forecast_ids"],
                "cohort": item["cohort"],
                "cohort_hash": item["cohort_hash"],
            }
            content_hash = _hash(record)
            existing = await db.scalar(select(AccuracySummaryLog.id).where(
                AccuracySummaryLog.content_hash == content_hash))
            if existing is not None:
                continue
            row = AccuracySummaryLog(
                as_of_date=as_of_date,
                program=program.upper(),
                horizon_days=horizon,
                formula_version=FORMULA_VERSION,
                score=item["score"],
                confidence=item["confidence"],
                sample_size=item["n"],
                observed_unit_count=item["observed_unit_count"],
                missing_window_count=item["missing_window_count"],
                post_ship_record_count=program_result["post_ship_record_count"],
                mae_days=item["mae_days"],
                bias_days=item["bias_days"],
                hit3_pct=item["hit3_pct"],
                hit7_pct=item["hit7_pct"],
                p80_sample_size=item["p80_sample_size"],
                p80_coverage_pct=item["p80_coverage_pct"],
                p80_wilson_low_pct=item["p80_wilson_low_pct"],
                p80_wilson_high_pct=item["p80_wilson_high_pct"],
                source_forecast_ids_json=_canonical(item["source_forecast_ids"]),
                cohort_json=_canonical(item["cohort"]),
                cohort_hash=item["cohort_hash"],
                content_hash=content_hash,
            )
            db.add(row)
            rows.append(row)
            created += 1
    await db.commit()
    return {"created": created, "rows": rows, "result": result}


async def accuracy_trend(
        db: AsyncSession, program: str, *, limit: int = 24) -> list[dict]:
    rows = (await db.execute(select(AccuracySummaryLog).where(
        AccuracySummaryLog.program == program.upper(),
    ).order_by(
        AccuracySummaryLog.as_of_date.desc(),
        AccuracySummaryLog.horizon_days,
        AccuracySummaryLog.id.desc(),
    ))).scalars().all()
    rows = rows[:limit]
    return [{
        "as_of_date": row.as_of_date.isoformat(),
        "captured_at": row.captured_at.isoformat(),
        "horizon_days": row.horizon_days,
        "formula_version": row.formula_version,
        "score": row.score,
        "confidence": row.confidence,
        "sample_size": row.sample_size,
        "mae_days": row.mae_days,
        "bias_days": row.bias_days,
        "hit7_pct": row.hit7_pct,
    } for row in reversed(rows)]
