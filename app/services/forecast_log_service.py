"""ForecastLog writes: idempotent daily build stamp + close backfill.

The ForecastLog table is the forward-accuracy store: one row per (build_date, serial). Each
"Refresh positions" stamps today's sim/p50/p80 for every live unit. Stamping is an idempotent
UPSERT on (build_date, serial) — clicking refresh three times in a day overwrites the same row
rather than appending, so the week-over-week slip diff (which keys on distinct build_date) stays
deterministic. When a unit ships, backfill sets actual_close + error_days on its prior rows.
"""
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ForecastLog
from app.services import forecast_service as FS
from app.config import settings


async def stamp_build(db: AsyncSession, ds, programs=None,
                      build_date: date | None = None) -> dict:
    """Idempotent daily stamp of the current forecast for every live (non-stalled) unit."""
    if programs is None:
        from app.services import program_service as PSVC
        programs = PSVC.program_order()
    bd = (build_date or ds.as_of().date()).isoformat()
    n_new = n_upd = 0
    from app.services.resource_profile import compile_profile
    compiled = await compile_profile(
        db, programs=programs, as_of=ds.as_of(), horizon_end=ds.as_of().date(),
        mode=settings.resource_source,
    )
    if compiled.snapshot_id is None:
        raise RuntimeError("Forecast stamping requires a persisted simulation snapshot")
    active_programs = list(compiled.epoch_ids)
    units_by_program = {
        program: [unit.as_sim_unit() for unit in ds.get_wip_units(program) if not unit.stalled]
        for program in active_programs
    }
    simulation = FS._pooled_sim(
        ds, active_programs, profile=compiled.scheduler_profile)
    from app.services.resource_profile import persist_replay_snapshot
    replay_snapshot = await persist_replay_snapshot(
        db, base_snapshot_id=compiled.snapshot_id,
        units_by_program=units_by_program, results=simulation,
    )
    for program in active_programs:
        from app.services import planning_basis_service as PLANNING
        from app.services import slot_service
        planning = await PLANNING.context_for_program(db, program)
        plan_targets = None
        if planning.configured_planning_basis == "PLAN_SLOTS":
            serials = {unit.serial for unit in ds.get_wip_units(program)}
            slots = await slot_service.get_slots(db, program, serials, commit=False)
            plan_targets = {slot.serial: slot.target_date for slot in slots if slot.serial}
        for f in FS.forecast_program(
                ds, program, programs=active_programs, simulation=simulation,
                planning=planning, plan_targets=plan_targets):
            if f.stalled or f.p50_date is None:
                continue
            existing = (await db.execute(
                select(ForecastLog).where(ForecastLog.build_date == bd,
                                          ForecastLog.serial == f.serial))).scalar_one_or_none()
            if existing is None:
                db.add(ForecastLog(
                    build_date=bd, program=program, serial=f.serial, so=f.so,
                    maxop_at_log=f.maxop, sim_finish_date=f.sim_finish_date,
                    p50_date=f.p50_date, p80_date=f.p80_date,
                    contract_date=f.contract_date, plan_target_date=f.plan_target_date,
                    comparison_target_date=f.comparison_target_date,
                    planning_basis=f.planning_basis, plan_label=f.plan_label,
                    model_epoch_key=f.epoch_key,
                    model_status=f.model_status,
                    simulation_snapshot_id=replay_snapshot.id))
                n_new += 1
            else:
                existing.maxop_at_log = f.maxop
                existing.sim_finish_date = f.sim_finish_date
                existing.p50_date = f.p50_date
                existing.p80_date = f.p80_date
                existing.contract_date = f.contract_date
                existing.plan_target_date = f.plan_target_date
                existing.comparison_target_date = f.comparison_target_date
                existing.planning_basis = f.planning_basis
                existing.plan_label = f.plan_label
                existing.model_epoch_key = f.epoch_key
                existing.model_status = f.model_status
                existing.simulation_snapshot_id = replay_snapshot.id
                n_upd += 1
    await db.commit()
    return dict(build_date=bd, stamped=n_new, updated=n_upd,
                programs=active_programs,
                skipped_programs=[p for p in programs if p not in active_programs])


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
        target = date.fromisoformat(r["contract_date"]) if r.get("contract_date") else None
        basis = ("PLAN_SLOTS" if r["program"] in {"ELEV", "RAD"}
                 else "CONTRACT_DATES" if r["program"] == "AEGIS" else None)
        db.add(ForecastLog(
            build_date=r["build_date"], program=r["program"], serial=r["serial"],
            so=r.get("so", ""), maxop_at_log=r.get("maxop_at_log"),
            p50_date=date.fromisoformat(fd) if fd else None,
            contract_date=(target if basis == "CONTRACT_DATES" else None),
            plan_target_date=(target if basis == "PLAN_SLOTS" else None),
            comparison_target_date=target, planning_basis=basis,
            plan_label=("RTG" if basis == "PLAN_SLOTS"
                        else "Contract" if basis == "CONTRACT_DATES" else None),
            model_status="EMPIRICAL"))
        n += 1
    await db.commit()
    return dict(seeded=True, rows=n)
