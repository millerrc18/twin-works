"""ForecastLog writes: idempotent daily build stamp + close backfill.

The ForecastLog table is the forward-accuracy store: one row per (build_date, serial). Each
"Refresh positions" stamps today's sim/p50/p80 for every live unit. Stamping is an idempotent
UPSERT on (build_date, serial) — clicking refresh three times in a day overwrites the same row
rather than appending, so the week-over-week slip diff (which keys on distinct build_date) stays
deterministic. When a unit ships, backfill sets actual_close + error_days on its prior rows.
"""
from datetime import date, datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ForecastLog
from app.services import forecast_service as FS


async def stamp_build(db: AsyncSession, ds, programs=("ELEV", "RAD", "AEGIS"),
                      build_date: date | None = None) -> dict:
    """Idempotent daily stamp of the current forecast for every live (non-stalled) unit."""
    bd = (build_date or ds.as_of().date()).isoformat()
    n_new = n_upd = 0
    for program in programs:
        for f in FS.forecast_program(ds, program):
            if f.stalled or f.p50 is None:
                continue
            existing = (await db.execute(
                select(ForecastLog).where(ForecastLog.build_date == bd,
                                          ForecastLog.serial == f.serial))).scalar_one_or_none()
            if existing is None:
                db.add(ForecastLog(
                    build_date=bd, program=program, serial=f.serial, so=f.so,
                    maxop_at_log=f.maxop, sim_finish_date=f.sim_finish,
                    p50_date=f.p50, p80_date=f.p80, contract_date=f.commit,
                    model_status=f.model_status))
                n_new += 1
            else:
                existing.maxop_at_log = f.maxop
                existing.sim_finish_date = f.sim_finish
                existing.p50_date = f.p50
                existing.p80_date = f.p80
                existing.contract_date = f.commit
                existing.model_status = f.model_status
                n_upd += 1
    await db.commit()
    return dict(build_date=bd, stamped=n_new, updated=n_upd)


async def backfill_close(db: AsyncSession, serial: str, actual_close: date) -> int:
    """Set actual_close + error_days (p50 - actual; + = pessimistic/late) on every prior
    un-backfilled log row for this serial. Returns rows touched. Idempotent."""
    rows = (await db.execute(
        select(ForecastLog).where(ForecastLog.serial == serial,
                                  ForecastLog.actual_close.is_(None)))).scalars().all()
    n = 0
    for r in rows:
        r.actual_close = actual_close
        r.error_days = (r.p50_date - actual_close).days if r.p50_date else None
        n += 1
    await db.commit()
    return n


async def seed_from_json_once(db: AsyncSession) -> dict:
    """One-time import of the legacy forecast_log.json single build into the DB table so the
    historical baseline build isn't lost when we cut slip over to the DB. No-op if DB already has
    rows or the file is absent."""
    import json
    from pathlib import Path
    existing = (await db.execute(select(ForecastLog.id).limit(1))).first()
    if existing is not None:
        return dict(seeded=False, reason="db not empty")
    p = Path(__file__).resolve().parent.parent.parent / "forecast_log.json"
    if not p.exists():
        return dict(seeded=False, reason="no json")
    log = json.load(open(p))
    n = 0
    for r in log:
        fd = r.get("forecast_date")
        db.add(ForecastLog(
            build_date=r["build_date"], program=r["program"], serial=r["serial"],
            so=r.get("so", ""), maxop_at_log=r.get("maxop_at_log"),
            p50_date=date.fromisoformat(fd) if fd else None,
            contract_date=(date.fromisoformat(r["contract_date"])
                           if r.get("contract_date") else None),
            model_status="EMPIRICAL"))
        n += 1
    await db.commit()
    return dict(seeded=True, rows=n)
