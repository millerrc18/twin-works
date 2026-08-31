"""Persistence and governance contracts for the physical resource registry."""
import asyncio
from datetime import date

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'resources.db').as_posix()}"
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def test_approved_assumption_is_immutable_and_successor_closes_prior_version(tmp_path):
    from app.services.resource_registry import (
        ApprovedRecordImmutable,
        add_assumption,
        supersede_assumption,
        update_assumption,
    )

    async def scenario(db):
        first = await add_assumption(
            db, subject_type="POOL", subject_key="59:TRI_A",
            parameter="shift_capacity", value={"1": 20}, unit="HOURS_PER_SHIFT",
            basis="OWNER_CONFIRMED", approval_status="APPROVED",
            commitment_grade="COMMITMENT_READY", effective_from=date(2026, 9, 1),
            owner="Plant 3", approver="Capacity owner",
        )
        with pytest.raises(ApprovedRecordImmutable):
            await update_assumption(db, first.id, value={"1": 24})
        second = await supersede_assumption(
            db, first.id, value={"1": 24}, effective_from=date(2026, 10, 1),
        )
        assert second.supersedes_id == first.id
        assert first.effective_to == date(2026, 9, 30)
        assert second.approval_status == "DRAFT"

    _run_scenario(tmp_path, scenario)


def test_direct_orm_edits_cannot_bypass_approved_record_immutability(tmp_path):
    from app.services.resource_registry import (
        ApprovedRecordImmutable,
        add_assumption,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db):
        pool = await create_pool(
            db, code="59:IMMUTABLE", site="59", name="Immutable test pool",
            resource_type="LABOR", capacity_unit="HOURS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="shift_capacity",
            value={"1": 8}, unit="HOURS_PER_SHIFT", basis="OWNER_CONFIRMED",
            approval_status="APPROVED", commitment_grade="COMMITMENT_READY",
            effective_from=date(2026, 9, 1), owner="Owner", approver="Approver",
        )
        capacity = await add_capacity_version(
            db, pool_id=pool.id, effective_from=date(2026, 9, 1),
            status="APPROVED", capacity_scope="GROSS_SITE",
            capacity_schedule={"1": 8}, assumption_id=assumption.id,
        )
        await db.commit()
        capacity_id = capacity.id

        assumption.value_json = '{"1": 99}'
        with pytest.raises(ApprovedRecordImmutable):
            await db.flush()
        await db.rollback()

        capacity = await db.get(type(capacity), capacity_id)
        capacity.capacity_schedule_json = '{"1": 99}'
        with pytest.raises(ApprovedRecordImmutable):
            await db.flush()

    _run_scenario(tmp_path, scenario)


def test_core_updates_cannot_bypass_approved_record_immutability(tmp_path):
    from app.models import ModelAssumption, ResourceCapacityVersion
    from app.services.resource_registry import add_assumption, add_capacity_version, create_pool

    async def scenario(db):
        pool = await create_pool(
            db, code="59:CORE_GUARD", site="59", name="Core guard",
            resource_type="LABOR", capacity_unit="HOURS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="shift_capacity",
            value={"1": 8}, unit="HOURS_PER_SHIFT", basis="OWNER_CONFIRMED",
            approval_status="APPROVED", commitment_grade="COMMITMENT_READY",
            effective_from=date(2026, 9, 1), owner="Owner", approver="Approver",
        )
        capacity = await add_capacity_version(
            db, pool_id=pool.id, effective_from=date(2026, 9, 1),
            status="APPROVED", capacity_scope="GROSS_SITE",
            capacity_schedule={"1": 8}, assumption_id=assumption.id,
        )
        await db.commit()
        assumption_id = assumption.id
        capacity_id = capacity.id

        with pytest.raises(DBAPIError):
            await db.execute(update(ModelAssumption).where(
                ModelAssumption.id == assumption_id).values(value_json='{"1":99}'))
        await db.rollback()
        with pytest.raises(DBAPIError):
            await db.execute(update(ResourceCapacityVersion).where(
                ResourceCapacityVersion.id == capacity_id).values(
                    capacity_schedule_json='{"1":99}'))

    _run_scenario(tmp_path, scenario)


def test_measured_actual_cannot_be_approved_with_insufficient_evidence(tmp_path):
    from app.services.resource_registry import InvalidAssumption, add_assumption

    async def scenario(db):
        with pytest.raises(InvalidAssumption, match="evidence"):
            await add_assumption(
                db, subject_type="POOL", subject_key="59:P3NDI",
                parameter="weekly_capacity", value=8, unit="HOURS_PER_WEEK",
                basis="MEASURED_ACTUAL", approval_status="APPROVED",
                commitment_grade="COMMITMENT_READY", effective_from=date(2026, 9, 1),
                evidence_count=1, minimum_evidence_count=8,
                owner="NDI", approver="NDI owner",
            )

    _run_scenario(tmp_path, scenario)


def test_capacity_versions_cannot_overlap_and_must_match_pool_unit(tmp_path):
    from app.services.resource_registry import (
        CapacityVersionOverlap,
        InvalidCapacityVersion,
        add_capacity_version,
        add_assumption,
        create_pool,
    )

    async def scenario(db):
        pool = await create_pool(
            db, code="59:TRI_A", site="59", name="Plant 3 Triband Assembly",
            resource_type="LABOR", capacity_unit="HOURS", work_center_no="TRI A",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="shift_capacity",
            value={"1": 20}, unit="HOURS_PER_SHIFT", basis="OWNER_CONFIRMED",
            approval_status="APPROVED", commitment_grade="COMMITMENT_READY",
            effective_from=date(2026, 9, 1), owner="Plant 3", approver="Owner",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=date(2026, 9, 1),
            effective_to=date(2026, 9, 30), status="APPROVED",
            capacity_scope="GROSS_SITE", capacity_schedule={"1": 20},
            assumption_id=assumption.id,
        )
        with pytest.raises(CapacityVersionOverlap):
            await add_capacity_version(
                db, pool_id=pool.id, effective_from=date(2026, 9, 15),
                status="DRAFT", capacity_scope="GROSS_SITE",
                capacity_schedule={"1": 24}, assumption_id=assumption.id,
            )
        with pytest.raises(InvalidCapacityVersion, match="slot"):
            await add_capacity_version(
                db, pool_id=pool.id, effective_from=date(2026, 10, 1),
                status="DRAFT", capacity_scope="GROSS_SITE", slot_count=2,
                assumption_id=assumption.id,
            )

    _run_scenario(tmp_path, scenario)


def test_approved_occupancy_binding_requires_valid_acquire_and_release_ops(tmp_path):
    from app.services.resource_registry import InvalidBinding, add_binding, create_pool

    async def scenario(db):
        pool = await create_pool(
            db, code="AERONOSE_ASSEMBLY_JIG", site="59", name="Aeronose Assembly Jigs",
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        with pytest.raises(InvalidBinding, match="release operation"):
            await add_binding(
                db, program="RAD", pool_id=pool.id, acquire_op=580, release_op=710,
                requirement_mode="OCCUPANCY", quantity=1,
                demand_source="FIXED", release_event="OP_COMPLETE", status="APPROVED",
                valid_operations={580, 590, 620},
            )

    _run_scenario(tmp_path, scenario)


def test_resource_coverage_reports_missing_provisional_and_stale_inputs(tmp_path):
    from app.services.resource_registry import (
        add_assumption,
        add_binding,
        add_capacity_version,
        create_pool,
        resource_coverage,
    )

    async def scenario(db):
        complete = await create_pool(
            db, code="59:TRI_A", site="59", name="TRI A",
            resource_type="LABOR", capacity_unit="HOURS", work_center_no="TRI A",
        )
        missing = await create_pool(
            db, code="59:P3NDI", site="59", name="P3 NDI",
            resource_type="LABOR", capacity_unit="HOURS", work_center_no="P3NDI",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=complete.code, parameter="shift_capacity",
            value={"1": 20}, unit="HOURS_PER_SHIFT", basis="OWNER_CONFIRMED",
            approval_status="APPROVED", commitment_grade="INTERNAL_ONLY",
            effective_from=date(2026, 8, 1), review_due_at=date(2026, 8, 15),
            owner="Plant 3", approver="Owner",
        )
        await add_capacity_version(
            db, pool_id=complete.id, effective_from=date(2026, 8, 1),
            status="APPROVED", capacity_scope="GROSS_SITE",
            capacity_schedule={"1": 20}, assumption_id=assumption.id,
        )
        for pool in (complete, missing):
            await add_binding(
                db, program="TESTCAP", pool_id=pool.id, acquire_op=4000,
                requirement_mode="EFFORT", quantity=1, demand_source="LABOR",
                release_event="OP_COMPLETE", status="APPROVED",
                valid_operations={4000},
            )
        issues = await resource_coverage(db, "TESTCAP", date(2026, 9, 1))
        assert {(issue.subject_key, issue.severity) for issue in issues} == {
            ("59:TRI_A", "PROVISIONAL"),
            ("59:P3NDI", "MISSING"),
        }
        tri_issue = next(issue for issue in issues if issue.subject_key == "59:TRI_A")
        assert "internal only" in tri_issue.reason.lower()
        assert "stale" in tri_issue.reason.lower()

    _run_scenario(tmp_path, scenario)


def test_resource_coverage_reports_unbound_program_work_centers(tmp_path, monkeypatch):
    from dataclasses import replace

    from app.engines.router_registry import registry
    from app.services.resource_registry import resource_coverage

    async def scenario(db):
        monkeypatch.setitem(
            registry.programs, "BCAFIN",
            replace(registry.spec("RAD"), code="BCAFIN", ops=(
                (3000, "Trim", "P3TRI", 1.6, "FIN"),
                (4000, "Assembly", "TRI A", 4.0, "FIN"),
            )),
        )
        issues = await resource_coverage(db, "BCAFIN", date(2026, 8, 31))
        assert {(issue.subject_key, issue.parameter, issue.severity) for issue in issues} == {
            ("P3TRI", "resource_binding", "MISSING"),
            ("TRI A", "resource_binding", "MISSING"),
        }

    _run_scenario(tmp_path, scenario)
