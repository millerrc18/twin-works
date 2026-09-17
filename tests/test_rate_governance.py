"""RATE-01a persisted context and governed staffing-evidence contracts."""
import asyncio
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    path = tmp_path / "rate-governance.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def _evidence():
    return {
        "schema_version": 1,
        "source_refs": ["owner://plant-3/rad-assembly/staffing/2026-09-17"],
        "captured_by": "IE owner",
        "captured_at": "2026-09-17T12:00:00+00:00",
        "method": "approved staffing and productive-hours review",
        "window": {"start": "2026-08-01", "end": "2026-08-31"},
        "sample_count": 20,
        "drift_policy": {"relative_threshold": 0.10, "minimum_samples": 8},
    }


def test_published_baseline_context_is_persisted_and_idempotent(tmp_path):
    from app.models import SimulationSnapshot
    from app.services.rate_governance import build_rate_baseline_context

    async def scenario(db):
        first = await build_rate_baseline_context(
            db,
            programs=["RAD"],
            baseline_kind="PUBLISHED",
            as_of=datetime(2026, 9, 17, 6),
            horizon_end=date(2027, 3, 1),
        )
        second = await build_rate_baseline_context(
            db,
            programs=["RAD"],
            baseline_kind="PUBLISHED",
            as_of=datetime(2026, 9, 17, 6),
            horizon_end=date(2027, 3, 1),
        )

        assert first.snapshot_id == second.snapshot_id
        assert first.content_hash == second.content_hash
        assert first.baseline_kind == "PUBLISHED"
        assert first.epochs["RAD"].epoch_key == "RAD:LEGACY"
        assert first.epochs["RAD"].definition_hash
        assert await db.get(SimulationSnapshot, first.snapshot_id) is not None

    _run_scenario(tmp_path, scenario)


def test_candidate_context_requires_exact_runnable_epoch_coverage(tmp_path):
    from app.services.model_epoch_service import ensure_incumbent_shadow_epochs
    from app.services.rate_governance import RateGovernanceError, build_rate_baseline_context

    async def scenario(db):
        candidates = await ensure_incumbent_shadow_epochs(db, ["ELEV", "RAD"])
        with pytest.raises(RateGovernanceError, match="exactly every selected program"):
            await build_rate_baseline_context(
                db,
                programs=["ELEV", "RAD"],
                baseline_kind="CANDIDATE",
                epoch_ids={"RAD": candidates["RAD"].epoch.id},
                as_of=datetime(2026, 9, 17, 6),
                horizon_end=date(2027, 3, 1),
            )

    _run_scenario(tmp_path, scenario)


def test_approved_skill_evidence_is_bound_to_real_labor_pool(tmp_path):
    from app.services.rate_governance import load_skill_evidence, record_skill_evidence
    from app.services.resource_registry import create_pool

    async def scenario(db):
        pool = await create_pool(
            db,
            code="59:RAD_ASSEMBLY_SKILL",
            site="59",
            name="Radome assembly skill pool",
            resource_type="LABOR",
            capacity_unit="HOURS",
            work_center_no="AEROA",
        )
        assumption = await record_skill_evidence(
            db,
            pool_code=pool.code,
            current_fte=Decimal("12"),
            productive_hours_per_fte=Decimal("118.5"),
            eligible_work_centers=("AEROA", "P3 QA"),
            eligible_shifts=(1, 3),
            learning_curve=(Decimal("0.50"), Decimal("0.75"), Decimal("1.00")),
            retention_yield=Decimal("0.90"),
            effective_from=date(2026, 9, 17),
            review_due_at=date(2026, 12, 17),
            owner="Operations owner",
            approver="IE owner",
            approval_status="APPROVED",
            evidence=_evidence(),
        )
        loaded = await load_skill_evidence(
            db, pool.code, as_of=date(2026, 9, 17))

        assert loaded.assumption_id == assumption.id
        assert loaded.skill_pool == pool.code
        assert loaded.current_fte == Decimal("12")
        assert loaded.productive_hours_per_fte == Decimal("118.5")
        assert loaded.eligible_work_centers == ("AEROA", "P3 QA")
        assert loaded.eligible_shifts == (1, 3)
        assert loaded.learning_curve == (
            Decimal("0.50"), Decimal("0.75"), Decimal("1.00"))
        assert loaded.retention_yield == Decimal("0.90")
        assert loaded.readiness == "READY"

    _run_scenario(tmp_path, scenario)


def test_skill_evidence_rejects_nonlabor_pool_and_invalid_curves(tmp_path):
    from app.services.rate_governance import RateGovernanceError, record_skill_evidence
    from app.services.resource_registry import create_pool

    async def scenario(db):
        tool = await create_pool(
            db, code="BAD_TOOL", site="59", name="Not labor",
            resource_type="TOOL", capacity_unit="SLOTS")
        with pytest.raises(RateGovernanceError, match="LABOR/HOURS"):
            await record_skill_evidence(
                db, pool_code=tool.code, current_fte=Decimal("1"),
                productive_hours_per_fte=Decimal("100"),
                eligible_work_centers=("AEROA",), eligible_shifts=(1,),
                learning_curve=(Decimal("1"),), retention_yield=Decimal("1"),
                effective_from=date(2026, 9, 17), review_due_at=date(2026, 12, 17),
                owner="Owner", approver="Approver", approval_status="APPROVED",
                evidence=_evidence())

        labor = await create_pool(
            db, code="BAD_CURVE", site="59", name="Bad curve",
            resource_type="LABOR", capacity_unit="HOURS")
        with pytest.raises(RateGovernanceError, match="nondecreasing"):
            await record_skill_evidence(
                db, pool_code=labor.code, current_fte=Decimal("1"),
                productive_hours_per_fte=Decimal("100"),
                eligible_work_centers=("AEROA",), eligible_shifts=(1,),
                learning_curve=(Decimal("0.8"), Decimal("0.7")),
                retention_yield=Decimal("1"), effective_from=date(2026, 9, 17),
                review_due_at=date(2026, 12, 17), owner="Owner", approver="Approver",
                approval_status="APPROVED", evidence=_evidence())

    _run_scenario(tmp_path, scenario)


def test_draft_or_stale_skill_evidence_is_not_ready(tmp_path):
    from app.services.rate_governance import load_skill_evidence, record_skill_evidence
    from app.services.resource_registry import create_pool

    async def scenario(db):
        pool = await create_pool(
            db, code="59:DRAFT_SKILL", site="59", name="Draft skill",
            resource_type="LABOR", capacity_unit="HOURS")
        await record_skill_evidence(
            db, pool_code=pool.code, current_fte=Decimal("2"),
            productive_hours_per_fte=Decimal("100"),
            eligible_work_centers=("AEROA",), eligible_shifts=(1,),
            learning_curve=(Decimal("0.5"), Decimal("1")),
            retention_yield=Decimal("0.9"), effective_from=date(2026, 9, 1),
            review_due_at=date(2026, 9, 10), owner="Owner", approver=None,
            approval_status="DRAFT", evidence=_evidence())

        loaded = await load_skill_evidence(
            db, pool.code, as_of=date(2026, 9, 17))
        assert loaded.readiness == "PROVISIONAL"
        assert "DRAFT" in loaded.readiness_reasons
        assert "PAST_REVIEW" in loaded.readiness_reasons

    _run_scenario(tmp_path, scenario)


def test_overlapping_skill_evidence_is_rejected(tmp_path):
    from app.services.rate_governance import RateGovernanceError, record_skill_evidence
    from app.services.resource_registry import create_pool

    async def scenario(db):
        pool = await create_pool(
            db, code="59:OVERLAP_SKILL", site="59", name="Overlap skill",
            resource_type="LABOR", capacity_unit="HOURS")
        common = dict(
            db=db, pool_code=pool.code, current_fte=Decimal("2"),
            productive_hours_per_fte=Decimal("100"),
            eligible_work_centers=("AEROA",), eligible_shifts=(1,),
            learning_curve=(Decimal("0.5"), Decimal("1")),
            retention_yield=Decimal("0.9"), review_due_at=date(2026, 12, 1),
            owner="Owner", approver="Approver", approval_status="APPROVED",
            evidence=_evidence())
        await record_skill_evidence(
            **common, effective_from=date(2026, 9, 1),
            effective_to=date(2026, 9, 30))
        with pytest.raises(RateGovernanceError, match="overlap"):
            await record_skill_evidence(
                **common, effective_from=date(2026, 9, 15), effective_to=None)

    _run_scenario(tmp_path, scenario)
