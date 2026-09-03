"""Governed draft inventory for known Aeronose tooling."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ModelAssumption,
    OperationResourceBinding,
    ResourceCapacityVersion,
    ResourcePool,
)
from app.services.assumption_evidence import canonical_evidence
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
REVIEWED_ON = date(2026, 9, 3)
REVIEW_DUE = date(2026, 10, 2)
OWNER = "Ryan Miller, Program Manager"
APPROVER = OWNER

TOOLING_REVIEW = {
    "AERONOSE_ASSEMBLY_JIG": {
        "dedicated_program": "RAD",
        "fungibility": "FUNGIBLE",
        "identity": "WI 3700ED0001-101 ASSY identifies 3700AF0001; Dup 1 uses larger drill-basket pins",
        "instance_setup": "Functional interchangeability owner-confirmed; larger-pin setup time and compatibility impact unknown",
        "binding_status": "Subring acquire/release is documented; top-assembly release remains unresolved",
    },
    "AERONOSE_HOLDING_FIXTURE": {
        "dedicated_program": "RAD",
        "fungibility": "FUNGIBLE",
        "identity": "Owner confirms holding fixtures are separate from paint dollies; controlled identity remains unresolved",
        "binding_status": "No controlled tool number or hold span found; dolly movements must not be used as proxy events",
    },
    "AERONOSE_TRIM_FIXTURE": {
        "dedicated_program": "RAD",
        "fungibility": "SINGLETON",
        "identity": "WI 3700ED0001-101 ASSY identifies trim fixture 3700TF0001-A01",
        "binding_status": "Acquire and release occur within op 580; a sub-operation release event is required",
    },
    "AERONOSE_SHELL_LAM_MOLD": {
        "dedicated_program": "RAD",
        "fungibility": "FUNGIBLE",
        "identity": "WI 3700ED0001-101 LAM identifies lamination mold 3700LM001",
        "binding_status": "Candidate hold is op 50 start through demold at op 570 start",
    },
    "AERONOSE_CORE_FORM_MOLD_SET": {
        "dedicated_program": "RAD",
        "fungibility": "COORDINATED_SET",
        "identity": "WI 3700COREKIT uses 3700LM0002, 3700LM0003, and a nose-forming mold",
        "binding_status": "Separate 3700COREKIT component stream must be linked before binding",
    },
}


def _calculation_method(code: str) -> str:
    review = TOOLING_REVIEW[code]
    return (
        "Owner-confirmed count, Aeronose dedication, and fungibility; controlled work "
        f"instructions and read-only IFS clocking reviewed 2026-09-03. {review['binding_status']}. "
        "Zero post-release lag is owner-reported but remains unapproved where clocking cannot "
        "isolate physical release. Maintenance exists but has no supplied production-impact window."
    )


def _operating_rules(code: str) -> dict:
    rules = {
        "post_release_lag_hours": 0,
        "post_release_lag_status": "OWNER_CONFIRMED_DRAFT_IFS_NOT_CAUSAL",
        "maintenance_status": "EXISTS_NO_KNOWN_PRODUCTION_IMPACT_WINDOWS_PENDING",
        "current_wip_assignments": "IFS_RECONSTRUCTION_PENDING",
    }
    if code == "AERONOSE_SHELL_LAM_MOLD":
        rules["provisional_availability"] = {
            "baseline_count": 3,
            "unavailable_quantity": 1,
            "effective_from": "2026-09-03T00:00:00-04:00",
            "expected_end_exclusive": "2026-09-26T00:00:00-04:00",
            "reason": "Tool-shop work for new core and plug locating template",
            "status": "OWNER_CONFIRMED_PROVISIONAL_ACTUAL_STATUS_PENDING",
            "early_return": "RESTORE_IMMEDIATELY",
        }
    return rules


def _evidence(code: str) -> dict:
    return {
        "schema_version": 1,
        "source_refs": [
            "owner://ryan-miller/aeronose-tooling/2026-09-03",
            "sharepoint://MFG-MMDCC/MVA-Manufacturing-Document-Library/GAC-Aeronose/current",
            "ifs://59/project/C48178/tooling-timing/2026-09-03",
        ],
        "captured_by": APPROVER,
        "captured_at": datetime(2026, 9, 3, tzinfo=timezone.utc).isoformat(),
        "method": _calculation_method(code),
        "review_decisions": TOOLING_REVIEW[code],
        "operating_rules": _operating_rules(code),
    }


def _apply_draft_review(assumption: ModelAssumption, code: str) -> bool:
    if assumption.approval_status != "DRAFT":
        return False
    method = _calculation_method(code)
    evidence_source = (
        "Ryan Miller tooling review 2026-09-03; controlled Aeronose WIs; "
        "read-only IFS clock timing audit"
    )
    evidence_json = canonical_evidence(
        _evidence(code), schema_version=1, require_complete=False
    )
    changed = any((
        assumption.owner != OWNER,
        assumption.approver != APPROVER,
        assumption.evidence_source != evidence_source,
        assumption.evidence_end != REVIEWED_ON,
        assumption.calculation_method != method,
        assumption.evidence_json != evidence_json,
    ))
    assumption.owner = OWNER
    assumption.approver = APPROVER
    assumption.evidence_source = evidence_source
    assumption.evidence_end = REVIEWED_ON
    assumption.calculation_method = method
    assumption.evidence_count = 3
    assumption.evidence_json = evidence_json
    return changed


async def seed_aeronose_tooling_drafts(db: AsyncSession) -> dict:
    """Persist reviewed draft facts without creating schedule-affecting bindings."""
    existing = {
        row.code: row for row in (await db.execute(select(ResourcePool).where(
            ResourcePool.code.in_([item[0] for item in AERONOSE_TOOLING])
        ))).scalars().all()
    }
    created = []
    retained = []
    reviewed = []
    for code, name, count in AERONOSE_TOOLING:
        if code in existing:
            pool = existing[code]
            if pool.resource_type != "TOOL" or pool.capacity_unit != "SLOTS":
                raise ResourceRegistryError(
                    f"Existing {code} is not a TOOL/SLOTS resource")
            version = await db.scalar(select(ResourceCapacityVersion).where(
                ResourceCapacityVersion.pool_id == pool.id
            ).order_by(ResourceCapacityVersion.id.desc()).limit(1))
            if version is None or version.slot_count != count:
                raise ResourceRegistryError(
                    f"Existing {code} does not match owner-confirmed count {count}")
            assumption = (
                await db.get(ModelAssumption, version.assumption_id)
                if version.assumption_id else None
            )
            if assumption and _apply_draft_review(assumption, code):
                reviewed.append(code)
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
                "Ryan Miller tooling review 2026-09-03; controlled Aeronose WIs; "
                "read-only IFS clock timing audit"
            ),
            evidence_end=REVIEWED_ON,
            calculation_method=_calculation_method(code),
            evidence_count=3, minimum_evidence_count=1,
            owner=OWNER, approver=APPROVER,
            review_due_at=REVIEW_DUE,
            evidence=_evidence(code),
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
        "reviewed": sorted(reviewed),
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
        evidence = json.loads(assumption.evidence_json) if assumption else {}
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
            "review_decisions": evidence.get("review_decisions"),
            "operating_rules": evidence.get("operating_rules"),
            "binding_count": binding_count,
        })
    return rows
