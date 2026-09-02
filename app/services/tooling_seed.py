"""Governed draft inventory for known Aeronose tooling."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ModelAssumption,
    OperationResourceBinding,
    ResourceCapacityVersion,
    ResourcePool,
)
from app.services.resource_registry import (
    ResourceRegistryError,
    add_assumption,
    add_capacity_version,
    create_pool,
)


AERONOSE_TOOLING = (
    ("AERONOSE_ASSEMBLY_JIG", "Aeronose assembly jigs", 2),
    ("AERONOSE_HOLDING_FIXTURE", "Aeronose holding fixtures", 2),
    ("AERONOSE_TRIM_FIXTURE", "Aeronose trim fixture", 1),
    ("AERONOSE_SHELL_LAM_MOLD", "Aeronose shell lamination molds", 3),
    ("AERONOSE_CORE_FORM_MOLD_SET", "Aeronose core-forming mold set", 1),
)

EFFECTIVE_FROM = date(2026, 9, 2)
REVIEW_DUE = date(2026, 10, 2)


async def seed_aeronose_tooling_drafts(db: AsyncSession) -> dict:
    """Persist counts as draft facts without creating schedule-affecting bindings."""
    existing = {
        row.code: row for row in (await db.execute(select(ResourcePool).where(
            ResourcePool.code.in_([item[0] for item in AERONOSE_TOOLING])
        ))).scalars().all()
    }
    created = []
    retained = []
    for code, name, count in AERONOSE_TOOLING:
        if code in existing:
            pool = existing[code]
            if pool.resource_type != "TOOL" or pool.capacity_unit != "SLOTS":
                raise ResourceRegistryError(
                    f"Existing {code} is not a TOOL/SLOTS resource")
            retained.append(code)
            continue
        pool = await create_pool(
            db, code=code, site="59", name=name,
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=code, parameter="slot_count",
            value=count, unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="DRAFT", commitment_grade="INTERNAL_ONLY",
            effective_from=EFFECTIVE_FROM,
            evidence_source=(
                "Ryan Miller tooling inventory supplied during TwinWorks planning"
            ),
            evidence_end=EFFECTIVE_FROM,
            calculation_method=(
                "Direct program-manager count; floor/process validation, fungibility, "
                "maintenance, changeover, and operation spans remain pending"
            ),
            evidence_count=1, minimum_evidence_count=1,
            owner="Ryan Miller, Program Manager",
            review_due_at=REVIEW_DUE,
        )
        capacity = await add_capacity_version(
            db, pool_id=pool.id, effective_from=EFFECTIVE_FROM,
            status="DRAFT", capacity_scope="NET_TRACKED", slot_count=count,
            calendar_policy={"status": "UNVERIFIED"},
            external_policy={"mode": "NOT_APPLICABLE"},
            assumption_id=assumption.id,
        )
        created.append({
            "code": code,
            "pool_id": pool.id,
            "assumption_id": assumption.id,
            "capacity_version_id": capacity.id,
            "slot_count": count,
        })
    bindings = int(await db.scalar(select(
        func.count(OperationResourceBinding.id)
    ).join(ResourcePool, OperationResourceBinding.pool_id == ResourcePool.id).where(
        ResourcePool.code.in_([item[0] for item in AERONOSE_TOOLING])
    )) or 0)
    if bindings:
        raise ResourceRegistryError(
            "Aeronose draft inventory unexpectedly has operation bindings")
    await db.flush()
    return {
        "created": created,
        "retained": sorted(retained),
        "binding_count": bindings,
    }


async def aeronose_tooling_inventory(db: AsyncSession) -> list[dict]:
    """Return the persisted pool/assumption/version state for audit scripts."""
    rows = []
    for code, name, expected_count in AERONOSE_TOOLING:
        pool = await db.scalar(select(ResourcePool).where(ResourcePool.code == code))
        if pool is None:
            rows.append({"code": code, "name": name, "present": False})
            continue
        version = await db.scalar(select(ResourceCapacityVersion).where(
            ResourceCapacityVersion.pool_id == pool.id
        ).order_by(ResourceCapacityVersion.id.desc()).limit(1))
        assumption = (await db.get(ModelAssumption, version.assumption_id)
                      if version and version.assumption_id else None)
        binding_count = int(await db.scalar(select(
            func.count(OperationResourceBinding.id)
        ).where(OperationResourceBinding.pool_id == pool.id)) or 0)
        rows.append({
            "code": code,
            "name": pool.name,
            "present": True,
            "resource_type": pool.resource_type,
            "capacity_unit": pool.capacity_unit,
            "slot_count": version.slot_count if version else None,
            "expected_count": expected_count,
            "capacity_status": version.status if version else None,
            "assumption_status": assumption.approval_status if assumption else None,
            "commitment_grade": assumption.commitment_grade if assumption else None,
            "owner": assumption.owner if assumption else None,
            "approver": assumption.approver if assumption else None,
            "review_due_at": (assumption.review_due_at.isoformat()
                              if assumption and assumption.review_due_at else None),
            "binding_count": binding_count,
        })
    return rows
