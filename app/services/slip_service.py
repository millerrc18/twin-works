"""Week-over-week slip: how a unit's forecast moved since the previous build.

Reads the ForecastLog DB table (the forward-accuracy store). For each serial, compares the latest
build's p50 to the most recent PRIOR distinct build's p50:
  slip_days > 0  -> slipped later since last review (bad)
  slip_days < 0  -> pulled in / recovered (good)
Returns {} gracefully when there's no prior snapshot (only one build so far), so the UI simply
shows no arrow until a second build accrues. Sync + stdlib-sqlite3 (hot path via matrix_service).
"""
import sqlite3
from datetime import date
from pathlib import Path
from app.config import settings


def _db_path() -> str:
    url = settings.database_url
    return url.split(":///", 1)[1] if ":///" in url else url


def _pd(s):
    try:
        return date.fromisoformat(s) if s else None
    except Exception:
        return None


def slip_by_serial() -> dict:
    """serial -> slip_days (latest p50 - prior p50). Empty if no prior build."""
    path = _db_path()
    if not Path(path).exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        builds = [r[0] for r in con.execute(
            "SELECT DISTINCT build_date FROM forecast_log "
            "WHERE p50_date IS NOT NULL ORDER BY build_date")]
        if len(builds) < 2:
            con.close()
            return {}
        latest, prior = builds[-1], builds[-2]

        def fc_map(bd):
            cur = con.execute(
                "SELECT serial, p50_date FROM forecast_log "
                "WHERE build_date=? AND p50_date IS NOT NULL", (bd,))
            return {r["serial"]: _pd(r["p50_date"]) for r in cur.fetchall()}

        now, was = fc_map(latest), fc_map(prior)
        con.close()
    except sqlite3.OperationalError:
        return {}
    out = {}
    for serial, f_now in now.items():
        f_was = was.get(serial)
        if f_now and f_was:
            out[serial] = (f_now - f_was).days
    return out
