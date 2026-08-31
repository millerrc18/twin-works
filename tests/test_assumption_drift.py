"""Evidence-schema, recertification, and audit-integrity tests."""
import asyncio
import json
from datetime import date

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'reviews.db').as_posix()}"
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def _evidence(*, threshold=None):
    payload = {
        "schema_version": 1,
        "source_refs": ["ifs://59/work-center/TEST"],
        "captured_by": "IE owner",
        "captured_at": "2026-08-01T12:00:00+00:00",
        "method": "four-week actual envelope",
        "window": {"start": "2026-07-01", "end": "2026-07-31"},
        "sample_count": 20,
    }
    if threshold is not None:
        payload["drift_policy"] = {
            "relative_threshold": threshold,
            "minimum_samples": 8,
        }
    return payload


def test_approved_assumption_requires_versioned_evidence(tmp_path):
    from app.services.resource_registry import InvalidAssumption, add_assumption

    async def scenario(db):
        with pytest.raises(InvalidAssumption, match="source_refs"):
            await add_assumption(
                db, subject_type="POOL", subject_key="59:TEST",
                parameter="capacity", value=100, unit="HOURS_PER_WEEK",
                basis="MEASURED_ACTUAL", approval_status="APPROVED",
                commitment_grade="COMMITMENT_READY", effective_from=date(2026, 8, 1),
                evidence_count=20, minimum_evidence_count=8,
                owner="IE owner", approver="Program owner",
                evidence={"schema_version": 1},
            )
        with pytest.raises(InvalidAssumption, match="Unsupported"):
            await add_assumption(
                db, subject_type="POOL", subject_key="59:TEST",
                parameter="capacity", value=100, unit="HOURS_PER_WEEK",
                basis="OWNER_CONFIRMED", approval_status="APPROVED",
                commitment_grade="COMMITMENT_READY", effective_from=date(2026, 8, 1),
                owner="IE owner", approver="Program owner",
                evidence_schema_version=99, evidence={"schema_version": 99},
            )
        invalid_time = _evidence()
        invalid_time["captured_at"] = "2026-08-01T12:00:00"
        with pytest.raises(InvalidAssumption, match="timezone"):
            await add_assumption(
                db, subject_type="POOL", subject_key="59:TEST",
                parameter="capacity", value=100, unit="HOURS_PER_WEEK",
                basis="OWNER_CONFIRMED", approval_status="APPROVED",
                commitment_grade="COMMITMENT_READY", effective_from=date(2026, 8, 1),
                owner="IE owner", approver="Program owner", evidence=invalid_time,
            )

    _run_scenario(tmp_path, scenario)


def test_review_generation_is_idempotent_and_does_not_mutate_assumption(tmp_path):
    from app.models import AssumptionReview
    from app.services.assumption_drift import DriftObservation, build_drift_report
    from app.services.resource_registry import add_assumption

    async def scenario(db):
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key="59:TEST",
            parameter="weekly_capacity", value=100, unit="HOURS_PER_WEEK",
            basis="MEASURED_ACTUAL", approval_status="APPROVED",
            commitment_grade="COMMITMENT_READY", effective_from=date(2026, 8, 1),
            review_due_at=date(2026, 8, 15), evidence_count=20,
            minimum_evidence_count=8, owner="IE owner", approver="Program owner",
            evidence=_evidence(threshold=0.1),
        )
        observation = DriftObservation(
            assumption_id=assumption.id, observed_value=75, sample_count=12,
            window_start=date(2026, 8, 1), window_end=date(2026, 8, 31),
            source_ref="ifs://clocking/59/TEST",
        )
        first = await build_drift_report(
            db, date(2026, 9, 1), observations=[observation])
        second = await build_drift_report(
            db, date(2026, 9, 1), observations=[observation])
        assert first.opened == 2
        assert second.opened == 0
        assert second.existing == 2
        assert await db.scalar(select(func.count(AssumptionReview.id))) == 2
        assert {row.review_type for row in first.reviews} == {"EXPIRY", "DRIFT"}
        assert assumption.approval_status == "APPROVED"
        assert json.loads(assumption.value_json) == 100

    _run_scenario(tmp_path, scenario)


def test_recertification_creates_successor_and_closes_review_once(tmp_path):
    from app.models import AssumptionReview, ModelAssumption, ResourceCapacityVersion
    from app.services.assumption_drift import build_drift_report, resolve_review
    from app.services.resource_registry import (
        ApprovedRecordImmutable, add_assumption, add_capacity_version, create_pool,
    )

    async def scenario(db):
        pool = await create_pool(
            db, code="59:TEST", site="59", name="Test pool",
            resource_type="LABOR", capacity_unit="HOURS", work_center_no="TEST",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key="59:TEST", parameter="capacity",
            value=100, unit="HOURS_PER_WEEK", basis="OWNER_CONFIRMED",
            approval_status="APPROVED", commitment_grade="COMMITMENT_READY",
            effective_from=date(2026, 8, 1), review_due_at=date(2026, 8, 31),
            owner="IE owner", approver="Program owner", evidence=_evidence(),
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=date(2026, 8, 1),
            status="APPROVED", capacity_scope="GROSS_SITE",
            capacity_schedule={"1": 100}, assumption_id=assumption.id,
        )
        report = await build_drift_report(db, date(2026, 9, 1))
        review = report.reviews[0]
        await resolve_review(
            db, review.id, resolution="RECERTIFIED", actor="IE owner",
            authority_role="IE_FLOOR", notes="Capacity remains representative",
            effective_from=date(2026, 9, 1), review_due_at=date(2026, 12, 1),
        )
        assert review.status == "RESOLVED"
        successor = await db.get(ModelAssumption, review.successor_assumption_id)
        assert successor.approval_status == "APPROVED"
        assert json.loads(successor.value_json) == 100
        assert assumption.approval_status == "SUPERSEDED"
        assert assumption.effective_to == date(2026, 8, 31)
        capacities = (await db.execute(select(ResourceCapacityVersion).order_by(
            ResourceCapacityVersion.effective_from))).scalars().all()
        assert [item.status for item in capacities] == ["SUPERSEDED", "APPROVED"]
        assert capacities[1].assumption_id == successor.id
        review_id = review.id
        await db.commit()

        review.resolution_notes = "tampered"
        with pytest.raises(ApprovedRecordImmutable):
            await db.flush()
        await db.rollback()
        with pytest.raises(DBAPIError):
            await db.execute(update(AssumptionReview).where(
                AssumptionReview.id == review_id).values(resolution_notes="raw tamper"))

    _run_scenario(tmp_path, scenario)


def test_missing_review_date_is_visible_readiness_debt(tmp_path):
    from app.services.assumption_drift import build_drift_report
    from app.services.resource_registry import (
        add_assumption, add_binding, add_capacity_version, create_pool, resource_coverage,
    )

    async def scenario(db):
        pool = await create_pool(
            db, code="59:NO_REVIEW", site="59", name="No review date",
            resource_type="LABOR", capacity_unit="HOURS", work_center_no="TEST",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="capacity",
            value={"1": 8}, unit="HOURS_PER_SHIFT", basis="OWNER_CONFIRMED",
            approval_status="APPROVED", commitment_grade="COMMITMENT_READY",
            effective_from=date(2026, 8, 1), owner="IE", approver="Program",
            evidence=_evidence(),
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=date(2026, 8, 1), status="APPROVED",
            capacity_scope="GROSS_SITE", capacity_schedule={"1": 8},
            assumption_id=assumption.id,
        )
        await add_binding(
            db, program="ELEV", pool_id=pool.id, acquire_op=100,
            requirement_mode="EFFORT", quantity=1, demand_source="LABOR",
            release_event="OP_COMPLETE", status="APPROVED", valid_operations={100},
        )
        report = await build_drift_report(db, date(2026, 9, 1))
        assert report.reviews[0].review_type == "MISSING_REVIEW_DATE"
        issues = await resource_coverage(db, "ELEV", date(2026, 9, 1))
        governed = next(issue for issue in issues if issue.subject_key == "59:NO_REVIEW")
        assert governed.severity == "PROVISIONAL"
        assert "MISSING_REVIEW_DATE" in governed.reason

    _run_scenario(tmp_path, scenario)
