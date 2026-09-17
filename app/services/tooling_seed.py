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
    ("AERONOSE_HOLDING_FIXTURE", "Aeronose holding fixture", 1),
    ("AERONOSE_TRIM_FIXTURE", "Aeronose trim fixture", 1),
    ("AERONOSE_SHELL_LAM_MOLD", "Aeronose shell lamination molds", 3),
    ("AERONOSE_CORE_FORM_MOLD_SET", "Aeronose core-forming mold set", 1),
    ("AERONOSE_PAINT_DOLLY", "Aeronose paint dollies", 6),
    ("AERONOSE_HANDLING_DOLLY", "Aeronose handling dollies", 9),
)

EFFECTIVE_FROM = date(2026, 9, 2)
REVIEWED_ON = date(2026, 9, 3)
SUPPLEMENTAL_REVIEWED_ON = date(2026, 9, 14)
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
        "fungibility": "SINGLETON",
        "identity": "One wooden, blue holding fixture; tool 3700HF0001; separate from paint and handling dollies",
        "binding_status": "Identity and count resolved; supported condition and acquire/release span remain unresolved",
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
    "AERONOSE_PAINT_DOLLY": {
        "dedicated_program": "RAD",
        "fungibility": "COMPATIBILITY_UNCONFIRMED",
        "identity": "Six tooling-list records: 3700HD0001, 3700HD0001 SN4, SN5, SN6, 3700HD0001-2, and 3700HD0001-3",
        "binding_status": "Used to move radomes from assembly through paint; occupancy span, serviceability, and capacity materiality remain unapproved",
    },
    "AERONOSE_HANDLING_DOLLY": {
        "dedicated_program": "RAD",
        "fungibility": "COMPATIBILITY_UNCONFIRMED",
        "identity": "Nine tooling-list records: 3700HD0003-DUP0 through 3700HD0003-DUP8",
        "binding_status": "Purpose, serviceability, and acquire/release span remain unresolved; no schedule binding exists",
    },
}

TOOLING_IDENTIFIERS = {
    "AERONOSE_HOLDING_FIXTURE": ["3700HF0001"],
    "AERONOSE_PAINT_DOLLY": [
        "3700HD0001", "3700HD0001 SN4", "3700HD0001 SN5",
        "3700HD0001 SN6", "3700HD0001-2", "3700HD0001-3",
    ],
    "AERONOSE_HANDLING_DOLLY": [
        f"3700HD0003-DUP{number}" for number in range(9)
    ],
}

SUPPLEMENTAL_CODES = {
    "AERONOSE_HOLDING_FIXTURE",
    "AERONOSE_SHELL_LAM_MOLD",
    "AERONOSE_PAINT_DOLLY",
    "AERONOSE_HANDLING_DOLLY",
}


def _reviewed_on(code: str) -> date:
    return SUPPLEMENTAL_REVIEWED_ON if code in SUPPLEMENTAL_CODES else REVIEWED_ON


def _evidence_source(code: str) -> str:
    return (
        f"Ryan Miller tooling review through {_reviewed_on(code).isoformat()}; "
        "controlled Aeronose WIs; read-only IFS clock timing audit"
    )


def _calculation_method(code: str) -> str:
    review = TOOLING_REVIEW[code]
    return (
        "Owner-confirmed inventory and Aeronose dedication; controlled work instructions and "
        f"read-only IFS clocking reviewed through {_reviewed_on(code).isoformat()}. "
        f"{review['binding_status']}. "
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
            "expected_end_exclusive": None,
            "prior_return_estimate": "on_or_before_2026-09-25",
            "return_control": "OWNER_CONFIRMATION_REQUIRED",
            "reason": "Mold is being used as a fabrication aid for the new core and plug locating template; no work is being performed on the mold",
            "status": "OWNER_CONFIRMED_IN_TOOL_SHOP_RETURN_DATE_PENDING",
            "early_return": "PRODUCTION_READY_IMMEDIATELY_ON_OWNER_CONFIRMATION",
        }
    return rules


def _evidence(code: str) -> dict:
    return {
        "schema_version": 1,
        "source_refs": [
            f"owner://ryan-miller/aeronose-tooling/{_reviewed_on(code).isoformat()}",
            "sharepoint://MFG-MMDCC/MVA-Manufacturing-Document-Library/GAC-Aeronose/current",
            "ifs://59/project/C48178/tooling-timing/2026-09-03",
        ],
        "captured_by": APPROVER,
        "captured_at": datetime.combine(
            _reviewed_on(code), datetime.min.time(), tzinfo=timezone.utc
        ).isoformat(),
        "method": _calculation_method(code),
        "review_decisions": TOOLING_REVIEW[code],
        "operating_rules": _operating_rules(code),
        "inventory_identifiers": TOOLING_IDENTIFIERS.get(code, []),
    }


def _apply_draft_review(assumption: ModelAssumption, code: str, count: int) -> bool:
    if assumption.approval_status != "DRAFT":
        return False
    method = _calculation_method(code)
    evidence_source = _evidence_source(code)
    evidence_json = canonical_evidence(
        _evidence(code), schema_version=1, require_complete=False
    )
    changed = any((
        assumption.owner != OWNER,
        assumption.approver != APPROVER,
        assumption.evidence_source != evidence_source,
        assumption.evidence_end != _reviewed_on(code),
        assumption.calculation_method != method,
        assumption.evidence_json != evidence_json,
        assumption.value_json != json.dumps(count, sort_keys=True),
    ))
    assumption.owner = OWNER
    assumption.approver = APPROVER
    assumption.evidence_source = evidence_source
    assumption.evidence_end = _reviewed_on(code)
    assumption.calculation_method = method
    assumption.evidence_count = 4 if code in SUPPLEMENTAL_CODES else 3
    assumption.evidence_json = evidence_json
    assumption.value_json = json.dumps(count, sort_keys=True)
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
    corrected = []
    for code, name, count in AERONOSE_TOOLING:
        if code in existing:
            pool = existing[code]
            if pool.resource_type != "TOOL" or pool.capacity_unit != "SLOTS":
                raise ResourceRegistryError(
                    f"Existing {code} is not a TOOL/SLOTS resource")
            pool.name = name
            version = await db.scalar(select(ResourceCapacityVersion).where(
                ResourceCapacityVersion.pool_id == pool.id
            ).order_by(ResourceCapacityVersion.id.desc()).limit(1))
            if version is None:
                raise ResourceRegistryError(
                    f"Existing {code} has no capacity version")
            assumption = (
                await db.get(ModelAssumption, version.assumption_id)
                if version.assumption_id else None
            )
            if version.slot_count != count:
                if (version.status != "DRAFT" or assumption is None
                        or assumption.approval_status != "DRAFT"):
                    raise ResourceRegistryError(
                        f"Existing {code} does not match owner-confirmed count {count}")
                version.slot_count = count
                corrected.append(code)
            if assumption and _apply_draft_review(assumption, code, count):
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
            evidence_source=_evidence_source(code),
            evidence_end=_reviewed_on(code),
            calculation_method=_calculation_method(code),
            evidence_count=(4 if code in SUPPLEMENTAL_CODES else 3),
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
        "corrected": sorted(corrected),
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
            "inventory_identifiers": evidence.get("inventory_identifiers", []),
            "binding_count": binding_count,
        })
    return rows
