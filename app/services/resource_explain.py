"""Read-only resource readiness and forecast explanation models."""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AssumptionReview,
    ModelAssumption,
    OperationResourceBinding,
    ResourceCapacityVersion,
    ResourcePool,
)
from app.services.resource_registry import (
    CoverageIssue,
    capacity_policy_coverage,
    resource_coverage,
)


def aggregate_readiness(issues: list[CoverageIssue]) -> str:
    if any(issue.severity == "MISSING" for issue in issues):
        return "INCOMPLETE"
    if issues:
        return "PROVISIONAL"
    return "COMPLETE"


async def _current_capacity(db: AsyncSession, pool_id: int, as_of: date):
    rows = (await db.execute(
        select(ResourceCapacityVersion).where(
            ResourceCapacityVersion.pool_id == pool_id,
            ResourceCapacityVersion.status == "APPROVED",
            ResourceCapacityVersion.effective_from <= as_of,
        )
    )).scalars().all()
    return next((row for row in rows if row.effective_to is None or row.effective_to >= as_of), None)


async def _resource_row(db: AsyncSession, pool: ResourcePool, as_of: date) -> dict:
    version = await _current_capacity(db, pool.id, as_of)
    assumption = (await db.get(ModelAssumption, version.assumption_id)
                  if version and version.assumption_id else None)
    consumers = sorted(set((await db.execute(
        select(OperationResourceBinding.program).where(
            OperationResourceBinding.pool_id == pool.id,
            OperationResourceBinding.status == "APPROVED",
        )
    )).scalars().all()))
    schedule = (json.loads(version.capacity_schedule_json)
                if version and version.capacity_schedule_json else None)
    calendar_policy = (json.loads(version.calendar_policy_json or "{}")
                       if version else None)
    external_policy = (json.loads(version.external_policy_json or "{}")
                       if version else None)
    readiness = "MISSING"
    open_reviews = []
    policy_issues = []
    if version and assumption and assumption.approval_status == "APPROVED":
        open_reviews = (await db.execute(
            select(AssumptionReview).where(
                AssumptionReview.assumption_id == assumption.id,
                AssumptionReview.status == "OPEN",
            ).order_by(AssumptionReview.opened_at, AssumptionReview.id)
        )).scalars().all()
        readiness = "COMPLETE"
        if (assumption.commitment_grade == "INTERNAL_ONLY" or
                (assumption.review_due_at and assumption.review_due_at < as_of)
                or open_reviews):
            readiness = "PROVISIONAL"
        policy_issues = await capacity_policy_coverage(db, pool, version, as_of)
        if any(issue.severity == "MISSING" for issue in policy_issues):
            readiness = "MISSING"
        elif policy_issues:
            readiness = "PROVISIONAL"
    return {
        "id": pool.id, "code": pool.code, "site": pool.site, "name": pool.name,
        "resource_type": pool.resource_type, "capacity_unit": pool.capacity_unit,
        "work_center_no": pool.work_center_no, "active": pool.active,
        "retired_at": pool.retired_at, "consumers": consumers,
        "capacity_schedule": schedule, "slot_count": version.slot_count if version else None,
        "capacity_scope": version.capacity_scope if version else None,
        "calendar_policy": calendar_policy, "external_policy": external_policy,
        "effective_from": version.effective_from if version else None,
        "effective_to": version.effective_to if version else None,
        "assumption_id": assumption.id if assumption else None,
        "basis": assumption.basis if assumption else None,
        "approval_status": assumption.approval_status if assumption else None,
        "commitment_grade": assumption.commitment_grade if assumption else None,
        "evidence_source": assumption.evidence_source if assumption else None,
        "evidence_start": assumption.evidence_start if assumption else None,
        "evidence_end": assumption.evidence_end if assumption else None,
        "calculation_method": assumption.calculation_method if assumption else None,
        "evidence_count": assumption.evidence_count if assumption else None,
        "owner": assumption.owner if assumption else None,
        "approver": assumption.approver if assumption else None,
        "review_due_at": assumption.review_due_at if assumption else None,
        "evidence_schema_version": assumption.evidence_schema_version if assumption else None,
        "evidence": json.loads(assumption.evidence_json) if assumption else None,
        "open_reviews": [
            {
                "review_key": review.review_key, "review_type": review.review_type,
                "reason": review.reason, "owner": review.owner,
                "opened_at": review.opened_at,
            }
            for review in open_reviews
        ],
        "policy_issues": [issue.__dict__ for issue in policy_issues],
        "readiness": readiness,
    }


async def list_resource_rows(db: AsyncSession, as_of: date) -> list[dict]:
    pools = (await db.execute(
        select(ResourcePool).order_by(ResourcePool.site, ResourcePool.code)
    )).scalars().all()
    return [await _resource_row(db, pool, as_of) for pool in pools]


async def get_resource_row(db: AsyncSession, code: str, as_of: date) -> dict | None:
    pool = (await db.execute(
        select(ResourcePool).where(ResourcePool.code == code)
    )).scalar_one_or_none()
    return await _resource_row(db, pool, as_of) if pool else None


async def program_readiness(db: AsyncSession, program: str, as_of: date) -> dict:
    issues = await resource_coverage(db, program, as_of)
    return {
        "program": program.upper(), "readiness": aggregate_readiness(issues),
        "issues": [issue.__dict__ for issue in issues],
    }


async def explain_unit_resources(db: AsyncSession, *, program: str, serial: str,
                                 maxop: int | None, as_of: date) -> dict:
    bindings = (await db.execute(
        select(OperationResourceBinding).where(
            OperationResourceBinding.program == program.upper(),
            OperationResourceBinding.status == "APPROVED",
        )
    )).scalars().all()
    remaining = [binding for binding in bindings if maxop is None or binding.acquire_op > maxop]
    pool_ids = sorted({binding.pool_id for binding in remaining})
    resources = []
    for pool_id in pool_ids:
        pool = await db.get(ResourcePool, pool_id)
        if pool:
            row = await _resource_row(db, pool, as_of)
            row["remaining_operations"] = sorted(
                {binding.acquire_op for binding in remaining if binding.pool_id == pool_id})
            resources.append(row)
    readiness = await program_readiness(db, program, as_of)
    return {
        "program": program.upper(), "serial": serial, "maxop": maxop,
        "readiness": readiness["readiness"], "issues": readiness["issues"],
        "resources": resources, "mode": "LEGACY",
        "note": "Legacy-equivalent resource values are explanatory; allocation remains legacy.",
    }
