"""Historical simulation replay remains exact after current-state changes."""
import asyncio
import json
from datetime import date

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'replay.db').as_posix()}"
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def test_replay_uses_frozen_inputs_routes_profile_and_expected_result(tmp_path, monkeypatch):
    from dataclasses import replace

    import routers as R
    from app.data.snapshot_source import SnapshotDataSource
    from app.engines import rtg_wrapper as wrapper
    from app.engines.router_registry import registry
    from app.models import SimulationSnapshot
    from app.services.resource_profile import (
        compile_profile, persist_replay_snapshot, replay_snapshot,
        seed_legacy_resources, verify_snapshot_integrity,
    )

    async def scenario(db):
        await seed_legacy_resources(db)
        ds = SnapshotDataSource(use_position_state=False)
        programs = ["ELEV", "RAD", "AEGIS"]
        units = {
            program: [unit.as_sim_unit() for unit in ds.get_wip_units(program)
                      if not unit.stalled]
            for program in programs
        }
        compiled = await compile_profile(
            db, programs=programs, as_of=ds.as_of(), horizon_end=date(2027, 3, 1),
            mode="LEGACY",
        )
        result = wrapper.run_pooled(
            units, ds.as_of(), profile=compiled.scheduler_profile)
        frozen = await persist_replay_snapshot(
            db, base_snapshot_id=compiled.snapshot_id,
            units_by_program=units, results=result,
        )
        first = await replay_snapshot(db, frozen.id)
        assert first.exact_match
        assert (await verify_snapshot_integrity(db, frozen.id))["replayable"] is True
        await db.commit()

        monkeypatch.setitem(R.WC_SHIFT, ("ELEV", "221"), {1: 1, 2: 1, 3: 1})
        monkeypatch.setitem(R.CURE_STATION_CAPACITIES, "P2_PAINT_BOOTH", 99)
        original = registry.programs["ELEV"]
        monkeypatch.setitem(
            registry.programs, "ELEV", replace(original, ops=original.ops[:-1]))
        second = await replay_snapshot(db, frozen.id)
        assert second.exact_match
        assert second.result_hash == first.result_hash

        with pytest.raises(DBAPIError):
            await db.execute(update(SimulationSnapshot).where(
                SimulationSnapshot.id == frozen.id).values(
                    profile_json=json.dumps({"tampered": True})))

    _run_scenario(tmp_path, scenario)
