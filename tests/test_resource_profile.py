"""Immutable resource-profile compilation and legacy parity coverage."""
import asyncio
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'profile.db').as_posix()}"
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def _seed_units():
    from app.data.snapshot_source import SnapshotDataSource

    ds = SnapshotDataSource(use_position_state=False)
    programs = ("ELEV", "RAD", "AEGIS")
    return ds, {
        program: [unit.as_sim_unit() for unit in ds.get_wip_units(program) if not unit.stalled]
        for program in programs
    }


def test_legacy_resource_seed_is_idempotent_and_db_shadow_matches_forecasts(tmp_path, monkeypatch):
    from sqlalchemy import event

    import routers as R
    from app.engines import rtg_wrapper as wrapper
    from app.models import ResourcePool, SimulationSnapshot
    from app.services.resource_profile import compile_profile, seed_legacy_resources

    async def scenario(db):
        first = await seed_legacy_resources(db)
        ds, units = _seed_units()
        baseline = wrapper.run_pooled(units, ds.as_of())
        statements = []
        event.listen(db.bind.sync_engine, "before_cursor_execute",
                     lambda _conn, _cursor, statement, _params, _ctx, _many:
                     statements.append(statement.strip().upper()))
        original = dict(R.WC_SHIFT[("ELEV", "221")])
        monkeypatch.setitem(R.WC_SHIFT, ("ELEV", "221"), {1: 999, 2: 999, 3: 999})
        second = await seed_legacy_resources(db)
        assert first["created_pools"] > 0
        assert second["created_pools"] == 0
        assert not any(statement.startswith(("UPDATE ", "INSERT ", "DELETE "))
                       for statement in statements)

        compiled = await compile_profile(
            db, programs=list(units), as_of=ds.as_of(),
            horizon_end=date(2027, 3, 1), mode="DB_SHADOW",
        )
        db_result = wrapper.run_pooled(units, ds.as_of(), profile=compiled.scheduler_profile)

        assert compiled.mode == "DB_SHADOW"
        assert compiled.readiness == "COMPLETE"
        assert len(compiled.snapshot_hash) == 64
        assert db_result == baseline
        assert (await db.scalar(select(func.count(ResourcePool.id)))) == first["created_pools"]
        assert (await db.scalar(select(func.count(SimulationSnapshot.id)))) == 1
        paint = next(row for row in compiled.pools.values()
                     if row["work_center_no"] == "221" and row["name"].startswith("Legacy ELEV"))
        assert paint["capacity_schedule"] == {"1": original[1], "2": original[2], "3": original[3]}

    _run_scenario(tmp_path, scenario)


def test_compiled_snapshot_hash_is_stable_and_persisted_once(tmp_path):
    from app.models import SimulationSnapshot
    from app.services.resource_profile import compile_profile, seed_legacy_resources

    async def scenario(db):
        await seed_legacy_resources(db)
        ds, units = _seed_units()
        args = dict(db=db, programs=list(units), as_of=ds.as_of(),
                    horizon_end=date(2027, 3, 1), mode="DB_SHADOW")
        first = await compile_profile(**args)
        second = await compile_profile(**args)
        assert first.snapshot_hash == second.snapshot_hash
        assert first.snapshot_id == second.snapshot_id
        assert (await db.scalar(select(func.count(SimulationSnapshot.id)))) == 1

    _run_scenario(tmp_path, scenario)


def test_legacy_mode_compiles_without_registry_rows(tmp_path):
    from app.services.resource_profile import compile_profile

    async def scenario(db):
        ds, units = _seed_units()
        compiled = await compile_profile(
            db, programs=list(units), as_of=ds.as_of(),
            horizon_end=date(2027, 3, 1), mode="LEGACY",
        )
        assert compiled.readiness == "COMPLETE"
        assert compiled.unresolved == ()
        assert compiled.scheduler_profile["shift_budgets"]

    _run_scenario(tmp_path, scenario)


def test_physical_pool_compiles_operation_identity_reserve_and_calendar(tmp_path):
    from app.models import OperationResourceBinding
    from app.services.model_epoch_service import (
        create_physical_shadow_epochs,
        ensure_legacy_epochs,
        published_epoch,
    )
    from app.services.resource_profile import (
        compile_profile,
        persist_replay_snapshot,
        replay_snapshot,
        seed_legacy_resources,
    )
    from app.services.resource_registry import (
        add_assumption,
        add_binding,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db):
        await seed_legacy_resources(db)
        legacy_binding = await db.scalar(select(OperationResourceBinding).where(
            OperationResourceBinding.program == "ELEV",
            OperationResourceBinding.acquire_op == 3800,
            OperationResourceBinding.status == "APPROVED",
        ))
        legacy_binding.status = "SUPERSEDED"
        pool = await create_pool(
            db, code="59:P2-PAINT", site="59", name="Plant 2 paint labor",
            resource_type="LABOR", capacity_unit="HOURS", work_center_no="PAINT-LABOR",
        )
        capacity_assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="shift_capacity",
            value={"1": 17, "2": 9, "3": 13}, unit="HOURS_PER_SHIFT",
            basis="OWNER_CONFIRMED", approval_status="APPROVED",
            commitment_grade="COMMITMENT_READY", effective_from=date(2026, 8, 19),
            owner="Floor owner", approver="IE owner",
        )
        reserve_assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="external_reserve",
            value={"1": 1, "2": 2, "3": 3}, unit="HOURS_PER_SHIFT",
            basis="OWNER_CONFIRMED", approval_status="APPROVED",
            commitment_grade="INTERNAL_ONLY", effective_from=date(2026, 8, 19),
            owner="Floor owner", approver="IE owner",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=date(2026, 8, 19),
            status="APPROVED", capacity_scope="GROSS_SITE",
            capacity_schedule={"1": 17, "2": 9, "3": 13},
            calendar_policy={
                "mode": "WEEKDAY_FACTORS",
                "factors": {str(day): 1.0 for day in range(7)},
                "exceptions": {}, "covered_until": "2027-03-01",
            },
            external_policy={
                "mode": "STATIC_RESERVE",
                "shift_reserve": {"1": 1, "2": 2, "3": 3},
                "assumption_id": reserve_assumption.id,
            },
            assumption_id=capacity_assumption.id,
        )
        await add_binding(
            db, program="ELEV", pool_id=pool.id, acquire_op=3800,
            requirement_mode="EFFORT", quantity=1, demand_source="LABOR",
            release_event="OP_COMPLETE", status="APPROVED",
            valid_operations={row[0] for row in __import__("routers").ELEVATOR_OPS},
        )
        await ensure_legacy_epochs(db, ["ELEV"])
        published_before = (await published_epoch(db, "ELEV")).epoch.id
        selection = (await create_physical_shadow_epochs(
            db, ["ELEV"], actor="Test", as_of=date(2026, 8, 25)))["ELEV"]
        assert selection.state == "OBSERVE"
        assert (await published_epoch(db, "ELEV")).epoch.id == published_before
        ds, _units = _seed_units()
        compiled = await compile_profile(
            db, programs=["ELEV"], as_of=ds.as_of(), horizon_end=date(2027, 3, 1),
            mode="DB_SHADOW", epoch_ids={"ELEV": selection.epoch.id},
        )

        assert compiled.scheduler_profile["allocation_mode"] == "PHYSICAL"
        assert compiled.scheduler_profile["operation_pools"][("ELEV", 3800)] == pool.code
        assert compiled.scheduler_profile["pool_shift_budgets"][pool.code] == {
            1: 17.0, 2: 9.0, 3: 13.0,
        }
        assert compiled.scheduler_profile["pool_external_reserves"][pool.code] == {
            1: 1.0, 2: 2.0, 3: 3.0,
        }
        assert compiled.scheduler_profile["pool_assumption_ids"][pool.code] == (
            capacity_assumption.id, reserve_assumption.id,
        )
        assert compiled.readiness == "PROVISIONAL"
        from app.engines.rtg_wrapper import run_pooled
        unit = next(item for item in _units["ELEV"] if (item["maxop"] or 0) >= 3700)
        physical_result = run_pooled(
            {"ELEV": [unit]}, ds.as_of(), profile=compiled.scheduler_profile)
        replay = await persist_replay_snapshot(
            db, base_snapshot_id=compiled.snapshot_id,
            units_by_program={"ELEV": [unit]}, results=physical_result,
        )
        assert (await replay_snapshot(db, replay.id)).exact_match

    _run_scenario(tmp_path, scenario)


def test_failed_forecast_stamp_rolls_back_new_snapshot(tmp_path, monkeypatch):
    from sqlalchemy import func

    from app.data.snapshot_source import SnapshotDataSource
    from app.models import SimulationSnapshot
    from app.services import forecast_log_service as forecast_log
    from app.services import forecast_service

    async def scenario(db):
        monkeypatch.setattr(
            forecast_service, "forecast_program",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stamp failed")),
        )
        with pytest.raises(RuntimeError, match="stamp failed"):
            await forecast_log.stamp_build(
                db, SnapshotDataSource(use_position_state=False), programs=["ELEV"])
        await db.rollback()
        assert (await db.scalar(select(func.count(SimulationSnapshot.id)))) == 0

    import pytest
    _run_scenario(tmp_path, scenario)
