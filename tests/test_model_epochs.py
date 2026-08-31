"""Lifecycle, publication, and immutable model-epoch governance tests."""
import asyncio
import json
import sqlite3
from datetime import date

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'epochs.db').as_posix()}"
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


async def _advance_to_commitment_ready(db, epoch_id):
    from app.services.model_epoch_service import transition_epoch

    await transition_epoch(
        db, epoch_id, to_state="OBSERVE", actor="Data admin",
        authority_role="DATA_ADMIN", rationale="Begin governed observation",
    )
    await transition_epoch(
        db, epoch_id, to_state="PROVISIONAL", actor="IE owner",
        authority_role="IE_FLOOR", rationale="Evidence coverage accepted",
    )
    return await transition_epoch(
        db, epoch_id, to_state="COMMITMENT_READY", actor="Master scheduler",
        authority_role="PROGRAM_SCHEDULING", rationale="Approved for publication",
    )


def test_transition_graph_and_authority_are_enforced(tmp_path):
    from app.services.model_epoch_service import (
        InvalidEpochTransition,
        ModelEpochError,
        create_epoch,
        current_transition,
        transition_epoch,
    )

    async def scenario(db):
        with pytest.raises(ModelEpochError, match="deterministic JSON"):
            await create_epoch(
                db, program="BCAFIN", label="Invalid definition",
                epoch_kind="CANDIDATE", resource_mode="DB_SHADOW",
                definition={"bad": float("nan")}, created_by="Data admin",
            )
        epoch = await create_epoch(
            db, program="BCAFIN", label="BCA observation candidate",
            epoch_kind="CANDIDATE", resource_mode="DB_SHADOW",
            definition={"routing_revision": "3"}, created_by="Data admin",
        )
        assert (await current_transition(db, epoch.id)).to_state == "DRAFT"
        with pytest.raises(InvalidEpochTransition, match="requires DATA_ADMIN"):
            await transition_epoch(
                db, epoch.id, to_state="OBSERVE", actor="Scheduler",
                authority_role="PROGRAM_SCHEDULING", rationale="Wrong authority",
            )
        with pytest.raises(InvalidEpochTransition, match="not allowed"):
            await transition_epoch(
                db, epoch.id, to_state="COMMITMENT_READY", actor="Scheduler",
                authority_role="PROGRAM_SCHEDULING", rationale="Skipped gates",
            )
        ready = await _advance_to_commitment_ready(db, epoch.id)
        assert ready.sequence == 4
        assert ready.to_state == "COMMITMENT_READY"

    _run_scenario(tmp_path, scenario)


def test_database_triggers_block_tampering_and_invalid_events(tmp_path):
    from app.models import ModelEpoch, ModelEpochTransition, ProgramEpochActivation
    from app.services.model_epoch_service import create_epoch

    async def scenario(db):
        epoch = await create_epoch(
            db, program="BCAFIN", label="Immutable candidate",
            epoch_kind="CANDIDATE", resource_mode="DB_SHADOW",
            definition={"version": 1}, created_by="Data admin",
        )
        await db.commit()
        epoch_id = epoch.id
        with pytest.raises(DBAPIError):
            await db.execute(update(ModelEpoch).where(
                ModelEpoch.id == epoch_id).values(label="Tampered"))
        await db.rollback()
        with pytest.raises(DBAPIError):
            await db.execute(insert(ModelEpochTransition).values(
                epoch_id=epoch_id, sequence=2, from_state="DRAFT",
                to_state="COMMITMENT_READY", authority_role="PROGRAM_SCHEDULING",
                actor="Bypass", rationale="Skip governance", evidence_json="{}",
            ))
        await db.rollback()
        draft = await db.scalar(select(ModelEpochTransition).where(
            ModelEpochTransition.epoch_id == epoch_id))
        with pytest.raises(DBAPIError):
            await db.execute(insert(ProgramEpochActivation).values(
                program="BCAFIN", epoch_id=epoch_id, transition_id=draft.id,
                action="PUBLISH", authority_role="PROGRAM_SCHEDULING",
                actor="Bypass", rationale="Publish a draft",
            ))

    _run_scenario(tmp_path, scenario)


def test_raw_sql_and_replace_cannot_bypass_append_only_guards(tmp_path):
    from app.data.snapshot_source import SnapshotDataSource
    from app.models import (
        ForecastConstraintEvent,
        ProgramEpochActivation,
        SimulationSnapshotEpoch,
    )
    from app.services.model_epoch_service import current_transition, ensure_legacy_epochs
    from app.services.resource_profile import compile_profile
    from app.services.resource_registry import create_pool

    ids = {}

    async def scenario(db):
        selected = (await ensure_legacy_epochs(db, ["ELEV"]))["ELEV"]
        ds = SnapshotDataSource(use_position_state=False)
        compiled = await compile_profile(
            db, programs=["ELEV"], as_of=ds.as_of(), horizon_end=date(2027, 3, 1),
            mode="LEGACY",
        )
        pool = await create_pool(
            db, code="RAW_GUARD", site="59", name="Raw guard",
            resource_type="LABOR", capacity_unit="HOURS",
        )
        event = ForecastConstraintEvent(
            simulation_snapshot_id=compiled.snapshot_id, serial="RAW-1", program="ELEV",
            pool_id=pool.id, event_type="WAIT", reason="Raw guard event",
        )
        db.add(event)
        await db.flush()
        transition = await current_transition(db, selected.epoch.id)
        activation = await db.scalar(
            select(ProgramEpochActivation)
            .where(ProgramEpochActivation.program == "ELEV")
            .order_by(ProgramEpochActivation.id.desc()))
        link = await db.scalar(select(SimulationSnapshotEpoch).where(
            SimulationSnapshotEpoch.simulation_snapshot_id == compiled.snapshot_id,
            SimulationSnapshotEpoch.program == "ELEV",
        ))
        ids.update(
            epoch=selected.epoch.id, transition=transition.id, activation=activation.id,
            snapshot=compiled.snapshot_id, snapshot_program=link.program, event=event.id,
        )
        await db.commit()

    _run_scenario(tmp_path, scenario)

    cases = [
        ("model_epoch", "id = ?", (ids["epoch"],), "label = label"),
        ("model_epoch_transition", "id = ?", (ids["transition"],),
         "rationale = rationale"),
        ("program_epoch_activation", "id = ?", (ids["activation"],),
         "rationale = rationale"),
        ("simulation_snapshot", "id = ?", (ids["snapshot"],),
         "readiness = readiness"),
        ("simulation_snapshot_epoch", "simulation_snapshot_id = ? AND program = ?",
         (ids["snapshot"], ids["snapshot_program"]), "model_epoch_id = model_epoch_id"),
        ("forecast_constraint_event", "id = ?", (ids["event"],), "reason = reason"),
    ]
    con = sqlite3.connect(tmp_path / "epochs.db")
    con.execute("PRAGMA recursive_triggers=OFF")
    try:
        for table, where, params, assignment in cases:
            statements = (
                f"UPDATE {table} SET {assignment} WHERE {where}",
                f"DELETE FROM {table} WHERE {where}",
                f"INSERT OR REPLACE INTO {table} SELECT * FROM {table} WHERE {where}",
            )
            for statement in statements:
                with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                    con.execute(statement, params)
                con.rollback()
    finally:
        con.close()


def test_candidate_never_replaces_published_legacy_without_activation(tmp_path):
    from app.models import ProgramEpochActivation
    from app.services.model_epoch_service import (
        EpochNotPublishable,
        _legacy_definition,
        create_epoch,
        ensure_legacy_epochs,
        publish_epoch,
        published_epoch,
        transition_epoch,
    )

    async def scenario(db):
        partial = await create_epoch(
            db, program="ELEV", label="Published legacy baseline",
            epoch_kind="LEGACY_BASELINE", resource_mode="LEGACY",
            definition=_legacy_definition("ELEV"), created_by="TwinWorks migration",
            epoch_key="ELEV:LEGACY",
        )
        await transition_epoch(
            db, partial.id, to_state="OBSERVE", actor="TwinWorks migration",
            authority_role="DATA_ADMIN", rationale="Interrupted bootstrap checkpoint",
        )
        await db.commit()
        legacy = (await ensure_legacy_epochs(db, ["ELEV"]))["ELEV"]
        assert legacy.state == "COMMITMENT_READY"
        legacy_id = legacy.epoch.id
        candidate = await create_epoch(
            db, program="ELEV", label="Resource registry candidate",
            epoch_kind="CANDIDATE", resource_mode="DB_SHADOW",
            definition={"resource_profile": "candidate-v1"},
            predecessor_epoch_id=legacy.epoch.id, created_by="Data admin",
        )
        ready_transition = await _advance_to_commitment_ready(db, candidate.id)
        candidate_id = candidate.id
        ready_transition_id = ready_transition.id
        assert (await published_epoch(db, "ELEV")).epoch.id == legacy.epoch.id

        await publish_epoch(
            db, candidate.id, actor="Master scheduler",
            authority_role="PROGRAM_SCHEDULING", rationale="Pilot accepted",
        )
        assert (await published_epoch(db, "ELEV")).epoch.id == candidate.id

        await transition_epoch(
            db, candidate.id, to_state="PAUSED", actor="Master scheduler",
            authority_role="PROGRAM_SCHEDULING", rationale="Evidence requires review",
        )
        await db.commit()
        assert await published_epoch(db, "ELEV") is None
        with pytest.raises(DBAPIError):
            await db.execute(insert(ProgramEpochActivation).values(
                program="ELEV", epoch_id=candidate_id,
                transition_id=ready_transition_id, action="PUBLISH",
                authority_role="PROGRAM_SCHEDULING", actor="Stale writer",
                rationale="Attempt stale activation",
            ))
        await db.rollback()
        with pytest.raises(EpochNotPublishable, match="COMMITMENT_READY"):
            await publish_epoch(
                db, candidate_id, actor="Master scheduler",
                authority_role="PROGRAM_SCHEDULING", action="ROLLBACK",
                rationale="Invalid rollback to paused epoch",
            )

        await transition_epoch(
            db, candidate_id, to_state="OBSERVE", actor="IE owner",
            authority_role="IE_FLOOR", rationale="Resume observation",
        )
        await transition_epoch(
            db, candidate_id, to_state="PROVISIONAL", actor="IE owner",
            authority_role="IE_FLOOR", rationale="Revalidated evidence",
        )
        await transition_epoch(
            db, candidate_id, to_state="COMMITMENT_READY", actor="Master scheduler",
            authority_role="PROGRAM_SCHEDULING", rationale="Ready again",
        )
        assert await published_epoch(db, "ELEV") is None
        await publish_epoch(
            db, legacy_id, actor="Master scheduler",
            authority_role="PROGRAM_SCHEDULING", action="ROLLBACK",
            rationale="Return to accepted legacy epoch",
        )
        assert (await published_epoch(db, "ELEV")).epoch.id == legacy_id
        assert await db.scalar(select(func.count(ProgramEpochActivation.id))) == 3

    _run_scenario(tmp_path, scenario)


def test_simulation_snapshot_materializes_exact_epoch_references(tmp_path):
    from app.data.snapshot_source import SnapshotDataSource
    from app.models import SimulationSnapshot, SimulationSnapshotEpoch
    from app.services.model_epoch_service import (
        create_epoch,
        ensure_legacy_epochs,
        published_epoch,
        transition_epoch,
    )
    from app.services.resource_profile import compile_profile, seed_legacy_resources

    async def scenario(db):
        await seed_legacy_resources(db)
        legacy = (await ensure_legacy_epochs(db, ["ELEV"]))["ELEV"]
        candidate = await create_epoch(
            db, program="ELEV", label="Shadow resource candidate",
            epoch_kind="CANDIDATE", resource_mode="DB_SHADOW",
            definition={"resource_profile": "candidate-v1"},
            predecessor_epoch_id=legacy.epoch.id, created_by="Data admin",
        )
        await transition_epoch(
            db, candidate.id, to_state="OBSERVE", actor="Data admin",
            authority_role="DATA_ADMIN", rationale="Begin shadow run",
        )
        ds = SnapshotDataSource(use_position_state=False)
        compiled = await compile_profile(
            db, programs=["ELEV"], as_of=ds.as_of(), horizon_end=date(2027, 3, 1),
            mode="DB_SHADOW", epoch_ids={"ELEV": candidate.id},
        )
        snapshot = await db.get(SimulationSnapshot, compiled.snapshot_id)
        payload = json.loads(snapshot.profile_json)
        assert payload["schema_version"] == 2
        assert payload["epochs"]["ELEV"]["epoch_key"] == candidate.epoch_key
        assert payload["epochs"]["ELEV"]["lifecycle_state"] == "OBSERVE"
        assert payload["epochs"]["ELEV"]["definition"]["definition"] == {
            "resource_profile": "candidate-v1",
        }
        ref = await db.scalar(select(SimulationSnapshotEpoch).where(
            SimulationSnapshotEpoch.simulation_snapshot_id == snapshot.id))
        assert ref.model_epoch_id == candidate.id
        assert (await published_epoch(db, "ELEV")).epoch.id == legacy.epoch.id

    _run_scenario(tmp_path, scenario)


def test_simulation_snapshots_are_append_only(tmp_path):
    from app.data.snapshot_source import SnapshotDataSource
    from app.models import SimulationSnapshot
    from app.services.resource_profile import compile_profile

    async def scenario(db):
        ds = SnapshotDataSource(use_position_state=False)
        compiled = await compile_profile(
            db, programs=["ELEV"], as_of=ds.as_of(), horizon_end=date(2027, 3, 1),
            mode="LEGACY",
        )
        await db.commit()
        with pytest.raises(DBAPIError):
            await db.execute(update(SimulationSnapshot).where(
                SimulationSnapshot.id == compiled.snapshot_id).values(readiness="INCOMPLETE"))

    _run_scenario(tmp_path, scenario)


def test_published_legacy_epoch_detects_runtime_registry_drift(tmp_path, monkeypatch):
    from dataclasses import replace

    from app.engines.router_registry import registry
    from app.services.model_epoch_service import EpochSelectionError, ensure_legacy_epochs

    async def scenario(db):
        await ensure_legacy_epochs(db, ["ELEV"])
        original = registry.programs["ELEV"]
        monkeypatch.setitem(
            registry.programs, "ELEV", replace(original, pack_op=original.pack_op + 1))
        with pytest.raises(EpochSelectionError, match="no longer matches"):
            await ensure_legacy_epochs(db, ["ELEV"])

    _run_scenario(tmp_path, scenario)
