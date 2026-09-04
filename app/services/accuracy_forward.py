"""Forward forecast accuracy from real prospective forecasts and physical pack dates.

This maturity track remains separate from the fixed-horizon Accuracy v1.0 score and from the
retrospective backtest. Each physical shipment is scored once at its earliest valid pre-pack
forecast. Same-day/post-pack logs and administrative-close-only units never count toward training.
"""
import json
import sqlite3
from datetime import date
from pathlib import Path
from statistics import mean

from app.config import settings


FORWARD_JSON = Path(__file__).resolve().parent.parent.parent / "accuracy_forward.json"


def _db_path() -> str:
    url = settings.database_url
    return url.split(":///", 1)[1] if ":///" in url else url


def _date(value):
    return date.fromisoformat(str(value)) if value else None


def compute_forward_accuracy() -> dict:
    """Score one earliest valid pre-pack P50 per physical shipment."""
    path = _db_path()
    if not Path(path).exists():
        return _empty()
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT f.id, f.program, f.serial, f.so, f.build_date,
                   f.p50_date, p.pack AS actual_pack, p.closed AS actual_close,
                   p.source AS position_source
            FROM forecast_log f
            LEFT JOIN position_state p
              ON p.program = f.program AND p.so = f.so
            ORDER BY f.program, f.so, f.build_date, f.id
        """).fetchall()
        con.close()
    except sqlite3.OperationalError:
        return _empty()

    missing_pack_units = {
        (row["program"], row["so"]) for row in rows
        if row["actual_close"] is not None and row["actual_pack"] is None
        and row["position_source"] == "ifs-sync"
    }
    post_ship_records = 0
    earliest = {}
    for row in rows:
        pack = _date(row["actual_pack"])
        build = _date(row["build_date"])
        p50 = _date(row["p50_date"])
        if (pack is None or build is None or p50 is None
                or row["position_source"] != "ifs-sync"):
            continue
        if build >= pack:
            post_ship_records += 1
            continue
        key = (row["program"], row["so"])
        if key not in earliest:
            earliest[key] = {
                "program": row["program"],
                "serial": row["serial"],
                "so": row["so"],
                "build_date": build,
                "actual_pack": pack,
                "error_days": (p50 - pack).days,
            }

    by_program = {}
    for row in earliest.values():
        by_program.setdefault(row["program"], []).append(row["error_days"])
    per_program = {program: _stats(errors) for program, errors in by_program.items()}
    counts = {program: len(errors) for program, errors in by_program.items()}
    result = {
        "by_program": per_program,
        "counts": counts,
        "overall": _stats([error for errors in by_program.values() for error in errors]),
        "exclusions": {
            "post_or_same_day_records": post_ship_records,
            "missing_physical_pack_units": len(missing_pack_units),
        },
        "note": (
            "Physical pack dates only; one earliest valid pre-pack forecast per program/shop "
            "order. Same-day/post-pack records are rejected. Kept separate from fixed-horizon "
            "Accuracy v1.0 and the retrospective backtest."
        ),
    }
    with FORWARD_JSON.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    return result


def _stats(errors):
    if not errors:
        return {"n": 0, "mae": None, "bias": None, "hit7": None}
    n = len(errors)
    return {
        "n": n,
        "mae": round(mean(abs(error) for error in errors), 1),
        "bias": round(mean(errors), 1),
        "hit7": round(100 * sum(abs(error) <= 7 for error in errors) / n),
    }


def _empty():
    return {
        "by_program": {},
        "counts": {},
        "overall": _stats([]),
        "exclusions": {
            "post_or_same_day_records": 0,
            "missing_physical_pack_units": 0,
        },
        "note": "No eligible physical-pack forward closes yet.",
    }


def forward_counts() -> dict:
    """Per-program count of eligible physical-pack forward ships."""
    return compute_forward_accuracy().get("counts", {})