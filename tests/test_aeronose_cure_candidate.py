"""Governed Aeronose op-775 cure successor contracts."""
import asyncio
import json
from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    path = tmp_path / "aeronose-cure.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def _op775_cures(definition):
    return [row for row in definition["routing"]["cures"] if row[0] == 775]


def test_no_station_definition_keeps_40_hour_cure():
    from app.services.aeronose_cure_candidate import build_cure_definition

    definition = build_cure_definition()

    assert _op775_cures(definition) == [[
        775,
        "GATE - Electrical Sealing 40hr (Shore A)",
        40,
        "op775 polysulfide 00200054000: WI MIN 40hr cure, Shore A>=35 gate "
        "(IFS mach 11.6hr understates) - dominant radome dwell",
    ]]
    assert definition["process_change"]["station_constraint"] == "NONE"
    assert definition["process_change"]["approval_status"] == "APPROVED_PHYSICAL_FACT"


def test_pending_drdi_definition_is_accelerated_but_not_observe_eligible():
    from app.services.aeronose_cure_candidate import (
        DrdiApprovalRequired,
        build_cure_definition,
        validate_observe_eligibility,
    )

    definition = build_cure_definition(drdi={"status": "PENDING"})

    assert [row[2] for row in _op775_cures(definition)] == [2, 8]
    assert definition["process_change"]["total_elapsed_hours"] == 10
    with pytest.raises(DrdiApprovalRequired, match="approved DRDI evidence"):
        validate_observe_eligibility(definition)


def test_approved_drdi_definition_requires_complete_approval_identity():
    from app.services.aeronose_cure_candidate import (
        DrdiApprovalRequired,
        build_cure_definition,
        validate_observe_eligibility,
    )

    definition = build_cure_definition(drdi={"status": "APPROVED"})

    with pytest.raises(DrdiApprovalRequired, match="identifiers"):
        validate_observe_eligibility(definition)


def test_successors_preserve_publication_and_gate_accelerated_observe(tmp_path):
    from app.services.aeronose_cure_candidate import ensure_cure_successors
    from app.services.model_epoch_service import current_transition, published_epoch

    async def scenario(db):
        candidates = await ensure_cure_successors(
            db,
            actor="Ryan Miller",
            drdi={"status": "PENDING"},
        )
        await db.commit()

        published = await published_epoch(db, "RAD")
        assert published.epoch.epoch_key == "RAD:LEGACY"
        assert (await current_transition(
            db, candidates.no_station_epoch_id)).to_state == "OBSERVE"
        assert (await current_transition(
            db, candidates.accelerated_epoch_id)).to_state == "DRAFT"
        no_station = await db.get(
            __import__("app.models", fromlist=["ModelEpoch"]).ModelEpoch,
            candidates.no_station_epoch_id,
        )
        no_station_payload = json.loads(no_station.definition_json)["definition"]
        assert no_station_payload["resource_registry"]["bindings"]

        approved = await ensure_cure_successors(
            db,
            actor="Ryan Miller",
            drdi={
                "status": "APPROVED",
                "identifiers": ["DRDI-TEST-001"],
                "approved_by": "Authorized engineering approver",
                "approved_at": "2026-09-17T12:00:00Z",
                "effective_from": "2026-09-17",
            },
        )
        await db.commit()

        accelerated = await db.get(__import__("app.models", fromlist=["ModelEpoch"]).ModelEpoch,
                                   approved.accelerated_epoch_id)
        payload = json.loads(accelerated.definition_json)["definition"]
        assert [row[2] for row in _op775_cures(payload)] == [2, 8]
        assert (await current_transition(db, accelerated.id)).to_state == "OBSERVE"
        assert (await published_epoch(db, "RAD")).epoch.epoch_key == "RAD:LEGACY"

    _run_scenario(tmp_path, scenario)


def test_cure_successor_detects_resource_registry_drift(tmp_path):
    from app.models import ResourcePool
    from app.services.aeronose_cure_candidate import ensure_cure_successors
    from app.services.model_epoch_service import EpochSelectionError
    from app.services.resource_profile import compile_profile

    async def scenario(db):
        candidates = await ensure_cure_successors(
            db, actor="Ryan Miller", drdi={"status": "PENDING"})
        pool = await db.scalar(select(ResourcePool).where(
            ResourcePool.code.like("LEGACY:RAD:%")).limit(1))
        pool.name = "Drifted resource name"
        await db.flush()

        with pytest.raises(EpochSelectionError, match="no longer matches"):
            await compile_profile(
                db,
                programs=["RAD"],
                as_of=datetime(2026, 9, 17, 6),
                horizon_end=date(2027, 3, 1),
                mode="DB_SHADOW",
                epoch_ids={"RAD": candidates.no_station_epoch_id},
            )

    _run_scenario(tmp_path, scenario)


def test_no_station_candidate_comparison_is_replayable(tmp_path):
    from app.services.aeronose_cure_candidate import (
        compare_cure_successor,
        ensure_cure_successors,
    )

    async def scenario(db):
        candidates = await ensure_cure_successors(
            db, actor="Ryan Miller", drdi={"status": "PENDING"})
        units = {
            "RAD": [
                {"serial": "R1", "so": "SO1", "maxop": 770,
                 "commit": date(2026, 9, 30), "program": "RAD"},
                {"serial": "R2", "so": "SO2", "maxop": 770,
                 "commit": date(2026, 9, 30), "program": "RAD"},
            ]
        }
        report = await compare_cure_successor(
            db,
            epoch_id=candidates.no_station_epoch_id,
            units_by_program=units,
            as_of=datetime(2026, 9, 17, 6),
            horizon_end=date(2026, 12, 31),
        )

        assert report.replay_exact
        assert report.changed_units > 0
        assert report.baseline_snapshot_id != report.candidate_snapshot_id
        assert all(delta.delta_hours <= 0 for delta in report.units)

    _run_scenario(tmp_path, scenario)


def test_compiled_candidate_uses_frozen_cure_and_removes_station(tmp_path):
    from app.services.aeronose_cure_candidate import ensure_cure_successors
    from app.services.resource_profile import compile_profile

    async def scenario(db):
        candidates = await ensure_cure_successors(
            db,
            actor="Ryan Miller",
            drdi={
                "status": "APPROVED",
                "identifiers": ["DRDI-TEST-001"],
                "approved_by": "Authorized engineering approver",
                "approved_at": "2026-09-17T12:00:00Z",
                "effective_from": "2026-09-17",
            },
        )
        compiled = await compile_profile(
            db,
            programs=["RAD"],
            as_of=datetime(2026, 9, 17, 6),
            horizon_end=date(2027, 3, 1),
            mode="DB_SHADOW",
            epoch_ids={"RAD": candidates.accelerated_epoch_id},
        )

        cures = compiled.scheduler_profile["routing_cures_map"]["RAD"]
        assert [row[2] for row in cures if row[0] == 775] == [2, 8]
        assert not any(
            program == "RAD" and opno == 775
            for program, opno, _label in compiled.scheduler_profile["cure_station_rules"]
        )

    _run_scenario(tmp_path, scenario)
