"""TwinWorks Accuracy v1.0 cohort, score, and snapshot contracts."""
import asyncio
import sqlite3
from datetime import date, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


UTC = timezone.utc


def _run_scenario(tmp_path, scenario):
    path = tmp_path / "accuracy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db, path)
        await engine.dispose()

    asyncio.run(run())


def _position(program: str, serial: str, so: str, pack: date):
    from app.models import PositionState

    return PositionState(
        so=so, program=program, serial=serial, maxop=None,
        closed=pack, pack=pack, source="ifs-sync",
    )


def _forecast(program: str, serial: str, so: str, build: date,
              p50: date, p80: date | None = None):
    from app.models import ForecastLog

    return ForecastLog(
        build_date=build.isoformat(), program=program, serial=serial, so=so,
        p50_date=p50, p80_date=p80, model_status="EMPIRICAL",
    )


def test_fixed_horizon_cohorts_exclude_post_ship_and_select_latest_in_window(tmp_path):
    from app.services.accuracy_score import compute_accuracy_scores

    async def scenario(db, _path):
        pack = date(2026, 9, 30)
        db.add(_position("ELEV", "LH 001", "SO-1", pack))
        # H7 window is 2026-09-17 through 2026-09-23; latest qualifying build wins.
        db.add_all([
            _forecast("ELEV", "LH 001", "SO-1", date(2026, 9, 16), date(2026, 9, 27)),
            _forecast("ELEV", "LH 001", "SO-1", date(2026, 9, 17), date(2026, 10, 4)),
            _forecast("ELEV", "LH 001", "SO-1", date(2026, 9, 22), date(2026, 10, 2),
                      date(2026, 10, 5)),
            _forecast("ELEV", "LH 001", "SO-1", date(2026, 9, 30), date(2026, 9, 30)),
            _forecast("ELEV", "LH 001", "SO-1", date(2026, 10, 1), date(2026, 10, 1)),
        ])
        await db.commit()

        result = await compute_accuracy_scores(
            db, programs=["ELEV", "RAD"], as_of=date(2026, 10, 2))
        elev = result["programs"]["ELEV"]
        h7 = elev["horizons"][7]
        h14 = elev["horizons"][14]
        h21 = elev["horizons"][21]

        assert h7["n"] == 1
        assert h7["source_forecast_ids"] == [3]
        assert h7["mae_days"] == 2.0
        assert h7["bias_days"] == 2.0
        assert h7["score"] == 89
        assert h7["confidence"] == "INSUFFICIENT"
        assert h7["p80_coverage_pct"] == 100.0
        assert h14["source_forecast_ids"] == [1]
        assert h14["bias_days"] == -3.0
        assert h21["n"] == 0
        assert h21["missing_window_count"] == 1
        assert elev["observed_unit_count"] == 1
        assert elev["post_ship_record_count"] == 2
        assert elev["headline_score"] is None
        assert result["programs"]["RAD"]["horizons"][7]["score"] is None

    _run_scenario(tmp_path, scenario)


def test_score_formula_confidence_headline_and_wilson_interval():
    from app.services.accuracy_score import (
        _headline,
        _score_errors,
        confidence_tier,
        wilson_interval,
    )

    metrics = _score_errors([0, 2, -2, 7, -7], [True, True, True, True, False])
    assert metrics["n"] == 5
    assert metrics["mae_days"] == 3.6
    assert metrics["bias_days"] == 0.0
    assert metrics["hit7_pct"] == 100.0
    assert metrics["score"] == 85
    assert confidence_tier(4) == "INSUFFICIENT"
    assert confidence_tier(5) == "PRELIMINARY"
    assert confidence_tier(12) == "DEVELOPING"
    assert confidence_tier(25) == "ESTABLISHED"
    low, high = wilson_interval(4, 5)
    assert 37.0 < low < 38.0
    assert 96.0 < high < 97.0

    horizons = {
        7: {"n": 5, "score": 90, "confidence": "PRELIMINARY"},
        14: {"n": 12, "score": 80, "confidence": "DEVELOPING"},
        21: {"n": 25, "score": 70, "confidence": "ESTABLISHED"},
    }
    headline = _headline(horizons)
    assert headline == {"score": 78, "confidence": "PRELIMINARY"}
    horizons[7]["n"] = 4
    assert _headline(horizons) is None


def test_daily_accuracy_snapshots_are_idempotent_append_only_and_provenanced(tmp_path):
    from app.models import AccuracySummaryLog, ImmutableEpochRecord
    from app.services.accuracy_score import capture_accuracy_summaries
    from app.services.assumption_drift import export_assumption_audit

    async def scenario(db, path):
        pack = date(2026, 9, 30)
        db.add(_position("AEGIS", "180", "SO-A", pack))
        db.add(_forecast(
            "AEGIS", "180", "SO-A", date(2026, 9, 21),
            date(2026, 10, 9), date(2026, 10, 10)))
        await db.commit()

        first = await capture_accuracy_summaries(
            db, programs=["AEGIS"], as_of=date(2026, 10, 2))
        second = await capture_accuracy_summaries(
            db, programs=["AEGIS"], as_of=date(2026, 10, 2))
        assert first["created"] == 3
        assert second["created"] == 0
        assert await db.scalar(select(func.count(AccuracySummaryLog.id))) == 3

        h7 = await db.scalar(select(AccuracySummaryLog).where(
            AccuracySummaryLog.program == "AEGIS",
            AccuracySummaryLog.horizon_days == 7,
        ))
        assert h7.score == 27
        assert h7.sample_size == 1
        assert h7.formula_version == "TW-ACC-1.0"
        assert h7.source_forecast_ids_json == "[1]"
        cohort = __import__("json").loads(h7.cohort_json)
        assert cohort[0]["so"] == "SO-A"
        assert cohort[0]["actual_ship_date"] == "2026-09-30"
        assert len(h7.content_hash) == 64
        audit = await export_assumption_audit(db)
        assert len(audit["accuracy_summaries"]) == 3

        h7.score = 100
        with pytest.raises(ImmutableEpochRecord):
            await db.flush()
        await db.rollback()

        con = sqlite3.connect(path)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                con.execute("UPDATE accuracy_summary_log SET score=100 WHERE id=1")
            con.rollback()
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                con.execute("DELETE FROM accuracy_summary_log WHERE id=1")
        finally:
            con.close()

    _run_scenario(tmp_path, scenario)


def test_forward_accuracy_counts_only_pre_ship_physical_pack_forecasts(tmp_path, monkeypatch):
    from app.config import settings
    from app.services import accuracy_forward

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'forward.db').as_posix()}"
    original_url = settings.database_url
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(_position("RAD", "515", "SO-R", date(2026, 9, 20)))
            db.add_all([
                _forecast("RAD", "515", "SO-R", date(2026, 9, 18), date(2026, 9, 25)),
                _forecast("RAD", "515", "SO-R", date(2026, 9, 20), date(2026, 9, 20)),
                _forecast("RAD", "515", "SO-R", date(2026, 9, 21), date(2026, 9, 21)),
            ])
            # Administrative close without a physical pack must never enter headline accuracy.
            from app.models import PositionState
            db.add(PositionState(
                so="SO-X", program="RAD", serial="516", closed=date(2026, 9, 22),
                pack=None, source="ifs-sync"))
            db.add(_forecast("RAD", "516", "SO-X", date(2026, 9, 18), date(2026, 9, 24)))
            await db.commit()

    try:
        asyncio.run(prepare())
        monkeypatch.setattr(settings, "database_url", database_url)
        monkeypatch.setattr(accuracy_forward, "FORWARD_JSON", tmp_path / "accuracy_forward.json")
        result = accuracy_forward.compute_forward_accuracy()
        assert result["counts"] == {"RAD": 1}
        assert result["by_program"]["RAD"]["mae"] == 5
        assert result["exclusions"]["post_or_same_day_records"] == 2
        assert result["exclusions"]["missing_physical_pack_units"] == 1
    finally:
        settings.database_url = original_url
        asyncio.run(engine.dispose())