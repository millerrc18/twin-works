"""PositionState: the mutable WIP/shipped layer, materialized from the wip_tables baseline
then updated by IFS syncs.

Two access modes on purpose:
  * ASYNC (seed / upsert / reset) — used by the sync service + admin routes (app is async).
  * SYNC read (load_state) — used by SnapshotDataSource, which is a synchronous hot path called
    on every matrix/forecast render. We read via stdlib sqlite3 against the same DB file (SQLite
    is local + fast) with a tiny mtime-gated cache so repeated renders don't re-query.

When the table is EMPTY, callers fall back to the wip_tables module baseline, so a fresh DB still
boots. `seed_from_baseline` copies the module rows in once; `reset` re-seeds (truncate + copy).
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import PositionState
from app.data import wip_tables as W


def _db_path() -> str:
    # settings.database_url = 'sqlite+aiosqlite:///C:/.../rtg_app_migrated.db'
    url = settings.database_url
    return url.split(":///", 1)[1] if ":///" in url else url


# ---------- SYNC read (hot path) ----------
_cache = {"mtime": None, "rows": None}


def _pd(s):
    return date.fromisoformat(s) if s else None


def load_state() -> dict:
    """Return {so: dict(program, serial, maxop, last_clock, due, closed, pack)} or {} if the
    table is empty / missing. Cached on the DB file mtime so renders don't re-read constantly."""
    path = _db_path()
    p = Path(path)
    if not p.exists():
        return {}
    mt = p.stat().st_mtime
    if _cache["mtime"] == mt and _cache["rows"] is not None:
        return _cache["rows"]
    rows = {}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT so,program,serial,maxop,last_clock,due,closed,pack FROM position_state")
        for r in cur.fetchall():
            rows[r["so"]] = dict(program=r["program"], serial=r["serial"], maxop=r["maxop"],
                                 last_clock=_pd(r["last_clock"]), due=_pd(r["due"]),
                                 closed=_pd(r["closed"]), pack=_pd(r["pack"]))
        con.close()
    except sqlite3.OperationalError:
        return {}          # table not created yet
    _cache["mtime"], _cache["rows"] = mt, rows
    return rows


def invalidate_cache():
    _cache["mtime"], _cache["rows"] = None, None


# ---------- ASYNC writes ----------
async def is_seeded(db: AsyncSession) -> bool:
    row = (await db.execute(select(PositionState.id).limit(1))).first()
    return row is not None


def _baseline_rows() -> list[dict]:
    """Flatten wip_tables baseline (WIP + SHIPPED) into PositionState dicts."""
    out = []
    for prog in ("ELEV", "RAD", "AEGIS"):
        for u in W.units_for(prog):                 # open WIP
            out.append(dict(so=u["so"], program=prog, serial=u["serial"],
                            maxop=u["maxop"], last_clock=W.LAST_CLOCK.get(u["so"]),
                            due=u["commit"], closed=None, pack=None, source="baseline"))
        for (serial, so, commit, close, pack, fx) in W.SHIPPED.get(prog, []):
            out.append(dict(so=so, program=prog, serial=serial, maxop=None,
                            last_clock=pack or close, due=commit, closed=close,
                            pack=pack, source="baseline"))
    return out


async def seed_from_baseline(db: AsyncSession, force: bool = False) -> dict:
    """Copy the wip_tables baseline into PositionState. No-op if already seeded unless force."""
    if not force and await is_seeded(db):
        return dict(seeded=False, reason="already populated")
    await db.execute(delete(PositionState))
    n = 0
    for r in _baseline_rows():
        db.add(PositionState(**r, synced_at=datetime.utcnow()))
        n += 1
    await db.commit()
    invalidate_cache()
    return dict(seeded=True, rows=n)


async def reset(db: AsyncSession) -> dict:
    """Truncate + re-seed from baseline (the 'revert to bootstrap' action)."""
    return await seed_from_baseline(db, force=True)


async def upsert(db: AsyncSession, so: str, program: str, serial: str, *, maxop=None,
                 last_clock=None, due=None, closed=None, pack=None, source="ifs-sync") -> None:
    """Insert or update one SO's state. Only overwrites fields explicitly passed (None-safe:
    closed/pack left as-is unless provided, so a position refresh doesn't wipe a ship date)."""
    row = (await db.execute(select(PositionState).where(PositionState.so == so))).scalar_one_or_none()
    if row is None:
        db.add(PositionState(so=so, program=program, serial=serial, maxop=maxop,
                             last_clock=last_clock, due=due, closed=closed, pack=pack,
                             source=source, synced_at=datetime.utcnow()))
        return
    row.program, row.serial, row.source = program, serial, source
    row.synced_at = datetime.utcnow()
    if maxop is not None:
        row.maxop = maxop
    if last_clock is not None:
        row.last_clock = last_clock
    if due is not None:
        row.due = due
    if closed is not None:
        row.closed = closed
    if pack is not None:
        row.pack = pack
