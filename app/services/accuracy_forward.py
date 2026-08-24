"""Forward accuracy — real prospective scoring, kept SEPARATE from the retrospective backtest.

For every ForecastLog row that has been backfilled with an actual_close, error = p50 - actual
(the same sign convention as the backtest: negative = optimistic/early). We score each SERIAL
ONCE using its EARLIEST logged forecast (the honest "how good was the forecast when we first
made it" number, not the easy day-before call). Emits accuracy_forward.json and returns per-program
forward-n so the train gate can count forward closes only (never blended with the backtest).
"""
import json
import sqlite3
from pathlib import Path
from statistics import mean
from app.config import settings

FORWARD_JSON = Path(__file__).resolve().parent.parent.parent / "accuracy_forward.json"


def _db_path() -> str:
    url = settings.database_url
    return url.split(":///", 1)[1] if ":///" in url else url


def compute_forward_accuracy() -> dict:
    """Read scored ForecastLog rows, one-per-serial (earliest build), group by program."""
    path = _db_path()
    if not Path(path).exists():
        return _empty()
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT program, serial, build_date, p50_date, actual_close, error_days "
            "FROM forecast_log WHERE actual_close IS NOT NULL AND error_days IS NOT NULL "
            "ORDER BY serial, build_date").fetchall()
        con.close()
    except sqlite3.OperationalError:
        return _empty()

    earliest = {}                       # serial -> row (first build seen wins)
    for r in rows:
        if r["serial"] not in earliest:
            earliest[r["serial"]] = r

    by_prog = {}
    for r in earliest.values():
        by_prog.setdefault(r["program"], []).append(r["error_days"])

    per_program, counts = {}, {}
    for prog, errs in by_prog.items():
        per_program[prog] = _stats(errs)
        counts[prog] = len(errs)

    result = dict(by_program=per_program, counts=counts,
                  overall=_stats([e for errs in by_prog.values() for e in errs]),
                  note="Forward-logged real ships only; scored once per serial at earliest "
                       "logged forecast. Kept separate from the retrospective backtest.")
    json.dump(result, open(FORWARD_JSON, "w"), indent=2)
    return result


def _stats(errs):
    if not errs:
        return dict(n=0, mae=None, bias=None, hit7=None)
    n = len(errs)
    return dict(n=n,
                mae=round(mean(abs(e) for e in errs), 1),
                bias=round(mean(errs), 1),
                hit7=round(100 * sum(1 for e in errs if abs(e) <= 7) / n))


def _empty():
    return dict(by_program={}, counts={}, overall=_stats([]), note="no forward closes yet")


def forward_counts() -> dict:
    """Per-program count of scored forward ships (the number the train gate should use)."""
    if FORWARD_JSON.exists():
        try:
            return json.load(open(FORWARD_JSON)).get("counts", {})
        except Exception:
            pass
    return compute_forward_accuracy().get("counts", {})
