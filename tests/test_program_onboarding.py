"""End-to-end safety coverage for DB-backed program onboarding."""
import asyncio
import os
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


os.environ.setdefault("RTG_DATA_SOURCE", "snapshot")

SEED_PROGRAMS = ("ELEV", "RAD", "AEGIS")


def _forecast_signature(data_source):
    from app.services import forecast_service as FS

    return {
        program: [
            (forecast.serial, forecast.sim_finish_date, forecast.p50_date,
             forecast.p80_date, forecast.delta_to_target)
            for forecast in FS.forecast_program(data_source, program)
        ]
        for program in SEED_PROGRAMS
    }


def test_onboarded_program_forecasts_but_does_not_publish_without_epoch(tmp_path, monkeypatch):
    """A new program can be modeled, but cannot enter the published forecast implicitly."""
    from app.config import settings
    from app.data import wip_tables as WIP
    from app.data.snapshot_source import SnapshotDataSource
    from app.engines import router_registry as RR
    from app.engines import rtg_wrapper as WRAPPER
    from app.models import ForecastLog, Program
    from app.services import forecast_log_service as FLOG
    from app.services import model_epoch_service as EPOCHS
    from app.services import position_state as POSITION
    from app.services import program_service as PROGRAMS

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'programs.db').as_posix()}"
    original_url = settings.database_url
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(PROGRAMS, "_export_snapshot_all", lambda: None)

    async def scenario():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            await PROGRAMS.seed_from_routers(db)
            await POSITION.seed_from_baseline(db)
            POSITION.invalidate_cache()
            seed_before = _forecast_signature(SnapshotDataSource())

            await EPOCHS.ensure_legacy_epochs(db, SEED_PROGRAMS)
            elev = RR.registry.spec("ELEV")
            staged = await PROGRAMS.create_program(
                db, code="ELEV", name="Unsafe direct replacement", plant="Plant 2",
                project_id="531335", part_nos=["72P5520501-029P01", "72P5520502-029P01"],
                ops=elev.ops, cures=elev.cures, milestones=elev.milestones,
                ceilings=elev.ceilings, crew_by_op=elev.crew_by_op,
                pack_op=elev.pack_op, ship_op=elev.ship_op, floor_op=elev.floor_op,
                dpas=elev.dpas,
            )
            stored_elev = await db.get(Program, "ELEV")
            assert staged["active_registry_changed"] is False
            assert staged["lifecycle_state"] == "DRAFT"
            assert stored_elev.name == "G500 Elevator"
            assert (await EPOCHS.published_epoch(db, "ELEV")).epoch.epoch_key == "ELEV:LEGACY"

            created = await PROGRAMS.create_program(
                db,
                code="TEST4",
                name="Synthetic Program",
                plant="Plant 2",
                project_id="TEST4",
                part_nos=["TEST4-PART"],
                ops=[
                    [100, "Shared paint preparation", "221", 2.0, "PREP"],
                    [200, "Independent finish", "TEST4WC", 2.0, "SHIP"],
                ],
                milestones=[["PREP", "Preparation"], ["SHIP", "Ship"]],
                ceilings=[["PREP", 100], ["SHIP", 200]],
                pack_op=200,
                ship_op=200,
            )
            assert created["lifecycle_state"] == "DRAFT"
            assert created["staged"] is True
            assert await EPOCHS.published_epoch(db, "TEST4") is None

            groups = [set(group) for group in WRAPPER.pool_groups(["ELEV", "RAD", "AEGIS", "TEST4"])]
            assert {"AEGIS", "ELEV", "TEST4"} in groups
            assert {"RAD"} in groups

            await POSITION.upsert(
                db,
                "TEST4-SO",
                "TEST4",
                "T4 001",
                maxop=100,
                last_clock=WIP.AS_OF.date(),
                due=date(2026, 10, 1),
                source="test",
            )
            await db.commit()
            POSITION.invalidate_cache()
            data_source = SnapshotDataSource()

            from app.services import forecast_service as FS
            synthetic = FS.forecast_program(data_source, "TEST4")
            assert [(row.serial, row.p50_date is not None) for row in synthetic] == [("T4 001", False)]
            assert _forecast_signature(data_source) == seed_before

            stamp = await FLOG.stamp_build(db, data_source)
            stamped = (await db.execute(
                select(ForecastLog).where(ForecastLog.program == "TEST4")
            )).scalars().all()
            assert stamped == []
            assert "TEST4" in stamp["skipped_programs"]
            assert stamp["programs"] == ["ELEV", "RAD", "AEGIS"]
            elev_log = await db.scalar(select(ForecastLog).where(
                ForecastLog.program == "ELEV"))
            assert elev_log.planning_basis == "PLAN_SLOTS"
            assert elev_log.plan_label == "RTG"
            assert elev_log.plan_target_date == elev_log.comparison_target_date
            assert elev_log.contract_date is not None
            assert elev_log.model_epoch_key == "ELEV:LEGACY"

    try:
        settings.database_url = database_url
        PROGRAMS.invalidate_cache()
        POSITION.invalidate_cache()
        RR.rebuild()
        asyncio.run(scenario())
    finally:
        settings.database_url = original_url
        PROGRAMS.invalidate_cache()
        POSITION.invalidate_cache()
        RR.rebuild()
        asyncio.run(engine.dispose())


def test_db_program_metadata_controls_dynamic_shared_capacity(tmp_path, monkeypatch):
    """New-program crew and DPAS metadata must affect a dynamically shared work center."""
    from app.config import settings
    from app.engines import router_registry as RR
    from app.engines import rtg_wrapper as WRAPPER
    from app.services import program_service as PROGRAMS

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'capacity.db').as_posix()}"
    original_url = settings.database_url
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(PROGRAMS, "_export_snapshot_all", lambda: None)

    async def scenario():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            await PROGRAMS.create_program(
                db,
                code="TEST4",
                name="DPAS synthetic program",
                plant="Plant 2",
                project_id="TEST4",
                part_nos=["TEST4-PART"],
                ops=[[100, "Shared work", "TEST-SHARED", 16.0, "SHIP"]],
                milestones=[["SHIP", "Ship"]],
                ceilings=[["SHIP", 100]],
                pack_op=100,
                ship_op=100,
                crew_by_op={100: 2.0},
                dpas=True,
            )
            await PROGRAMS.create_program(
                db,
                code="TEST5",
                name="Standard synthetic program",
                plant="Plant 2",
                project_id="TEST5",
                part_nos=["TEST5-PART"],
                ops=[[100, "Shared work", "TEST-SHARED", 16.0, "SHIP"]],
                milestones=[["SHIP", "Ship"]],
                ceilings=[["SHIP", 100]],
                pack_op=100,
                ship_op=100,
            )

            result = WRAPPER.run_pooled(
                {
                    "TEST4": [dict(serial="T4", so="T4-SO", maxop=0,
                                   commit=date(2026, 8, 24), program="TEST4")],
                    "TEST5": [dict(serial="T5", so="T5-SO", maxop=0,
                                   commit=date(2026, 8, 20), program="TEST5")],
                },
                datetime(2026, 8, 25, 6, 0),
            )

            assert result["T4"]["finish"] < result["T5"]["finish"]

    try:
        settings.database_url = database_url
        PROGRAMS.invalidate_cache()
        RR.rebuild()
        asyncio.run(scenario())
    finally:
        settings.database_url = original_url
        PROGRAMS.invalidate_cache()
        RR.rebuild()
        asyncio.run(engine.dispose())
