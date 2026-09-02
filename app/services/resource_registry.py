"""Persistence and governance services for physical resources and model assumptions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AssumptionReview,
    ApprovedRecordImmutable,
    ModelAssumption,
    OperationResourceBinding,
    ResourceCapacityVersion,
    ResourcePool,
)
from app.services.assumption_evidence import (
    EvidenceValidationError,
    build_evidence,
    canonical_evidence,
)


RESOURCE_TYPES = {"LABOR", "MACHINE", "TOOL", "CURE_STATION", "SPACE"}
CAPACITY_UNITS = {"HOURS", "SLOTS"}
ASSUMPTION_BASES = {
    "IFS_FACT", "MEASURED_ACTUAL", "DERIVED_ESTIMATE", "OWNER_CONFIRMED",
    "PROVISIONAL_GUESS",
}
APPROVAL_STATUSES = {"DRAFT", "APPROVED", "UNDER_REVIEW", "SUPERSEDED"}
COMMITMENT_GRADES = {"COMMITMENT_READY", "INTERNAL_ONLY"}
CAPACITY_STATUSES = {"DRAFT", "APPROVED", "SUPERSEDED"}
CAPACITY_SCOPES = {"GROSS_SITE", "NET_TRACKED"}
REQUIREMENT_MODES = {"EFFORT", "OCCUPANCY"}
DEMAND_SOURCES = {"LABOR", "MACHINE", "FIXED"}
RELEASE_EVENTS = {"OP_START", "OP_COMPLETE", "CURE_COMPLETE", "ROUTE_COMPLETE"}


class ResourceRegistryError(ValueError):
    pass


class InvalidAssumption(ResourceRegistryError):
    pass


class InvalidCapacityVersion(ResourceRegistryError):
    pass


class CapacityVersionOverlap(ResourceRegistryError):
    pass


class InvalidBinding(ResourceRegistryError):
    pass


@dataclass(frozen=True)
class CoverageIssue:
    subject_key: str
    parameter: str
    severity: str
    reason: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _policy_date(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _require_choice(value: str, allowed: set[str], field: str, exc_type):
    if value not in allowed:
        raise exc_type(f"Invalid {field}: {value}")


async def create_pool(db: AsyncSession, *, code: str, site: str, name: str,
                      resource_type: str, capacity_unit: str,
                      work_center_no: str | None = None) -> ResourcePool:
    resource_type = resource_type.upper()
    capacity_unit = capacity_unit.upper()
    _require_choice(resource_type, RESOURCE_TYPES, "resource type", ResourceRegistryError)
    _require_choice(capacity_unit, CAPACITY_UNITS, "capacity unit", ResourceRegistryError)
    if resource_type in {"LABOR", "MACHINE"} and capacity_unit != "HOURS":
        raise ResourceRegistryError(f"{resource_type} pools require HOURS")
    if resource_type in {"TOOL", "CURE_STATION", "SPACE"} and capacity_unit != "SLOTS":
        raise ResourceRegistryError(f"{resource_type} pools require SLOTS")
    pool = ResourcePool(
        code=code.strip(), site=site.strip(), name=name.strip(),
        resource_type=resource_type, capacity_unit=capacity_unit,
        work_center_no=(work_center_no.strip() if work_center_no else None), active=True,
    )
    db.add(pool)
    await db.flush()
    return pool


def _validate_assumption(*, basis: str, approval_status: str, commitment_grade: str,
                         evidence_count: int | None, minimum_evidence_count: int | None,
                         owner: str | None, approver: str | None) -> None:
    _require_choice(basis, ASSUMPTION_BASES, "assumption basis", InvalidAssumption)
    _require_choice(approval_status, APPROVAL_STATUSES, "approval status", InvalidAssumption)
    _require_choice(commitment_grade, COMMITMENT_GRADES, "commitment grade", InvalidAssumption)
    if approval_status == "APPROVED":
        if not owner or not approver:
            raise InvalidAssumption("Approved assumptions require owner and approver")
        if (basis == "MEASURED_ACTUAL" and minimum_evidence_count is not None and
                (evidence_count or 0) < minimum_evidence_count):
            raise InvalidAssumption("Measured-actual evidence count is below the approval minimum")


async def add_assumption(db: AsyncSession, *, subject_type: str, subject_key: str,
                         parameter: str, value, unit: str | None, basis: str,
                         approval_status: str = "DRAFT",
                         commitment_grade: str = "INTERNAL_ONLY",
                         effective_from: date, effective_to: date | None = None,
                         evidence_source: str | None = None,
                         evidence_start: date | None = None,
                         evidence_end: date | None = None,
                         calculation_method: str | None = None,
                         evidence_count: int | None = None,
                         minimum_evidence_count: int | None = None,
                         owner: str | None = None, approver: str | None = None,
                         review_due_at: date | None = None,
                         supersedes_id: int | None = None,
                         evidence_schema_version: int = 1,
                         evidence: dict | None = None) -> ModelAssumption:
    basis = basis.upper()
    approval_status = approval_status.upper()
    commitment_grade = commitment_grade.upper()
    _validate_assumption(
        basis=basis, approval_status=approval_status,
        commitment_grade=commitment_grade, evidence_count=evidence_count,
        minimum_evidence_count=minimum_evidence_count, owner=owner, approver=approver,
    )
    if effective_to is not None and effective_to < effective_from:
        raise InvalidAssumption("effective_to must not precede effective_from")
    if evidence is None:
        evidence = build_evidence(
            schema_version=evidence_schema_version,
            subject_type=subject_type.upper(), subject_key=subject_key,
            parameter=parameter, basis=basis, evidence_source=evidence_source,
            evidence_start=evidence_start, evidence_end=evidence_end,
            calculation_method=calculation_method, evidence_count=evidence_count,
            owner=owner, approver=approver, effective_from=effective_from,
        )
    try:
        evidence_json = canonical_evidence(
            evidence, schema_version=evidence_schema_version,
            require_complete=approval_status == "APPROVED",
        )
    except EvidenceValidationError as exc:
        raise InvalidAssumption(str(exc)) from exc
    row = ModelAssumption(
        subject_type=subject_type.upper(), subject_key=subject_key, parameter=parameter,
        value_json=json.dumps(value, sort_keys=True), unit=unit, basis=basis,
        approval_status=approval_status, commitment_grade=commitment_grade,
        evidence_source=evidence_source, evidence_start=evidence_start,
        evidence_schema_version=evidence_schema_version, evidence_json=evidence_json,
        evidence_end=evidence_end, calculation_method=calculation_method,
        evidence_count=evidence_count, minimum_evidence_count=minimum_evidence_count,
        owner=owner, approver=approver,
        approved_at=(_utcnow() if approval_status == "APPROVED" else None),
        review_due_at=review_due_at, effective_from=effective_from,
        effective_to=effective_to, supersedes_id=supersedes_id,
    )
    db.add(row)
    await db.flush()
    return row


async def update_assumption(db: AsyncSession, assumption_id: int, **changes) -> ModelAssumption:
    row = await db.get(ModelAssumption, assumption_id)
    if row is None:
        raise InvalidAssumption("Assumption not found")
    if row.approval_status == "APPROVED":
        raise ApprovedRecordImmutable("Approved assumptions must be superseded")
    if "value" in changes:
        row.value_json = json.dumps(changes.pop("value"), sort_keys=True)
    for key, value in changes.items():
        if not hasattr(row, key):
            raise InvalidAssumption(f"Unknown assumption field: {key}")
        setattr(row, key, value)
    await db.flush()
    return row


async def supersede_assumption(db: AsyncSession, assumption_id: int, *, value,
                               effective_from: date, **changes) -> ModelAssumption:
    prior = await db.get(ModelAssumption, assumption_id)
    if prior is None:
        raise InvalidAssumption("Assumption not found")
    if effective_from <= prior.effective_from:
        raise InvalidAssumption("Successor must start after the prior assumption")
    prior.effective_to = effective_from - timedelta(days=1)
    prior.approval_status = "SUPERSEDED"
    values = dict(
        subject_type=prior.subject_type, subject_key=prior.subject_key,
        parameter=prior.parameter, value=value, unit=prior.unit, basis=prior.basis,
        approval_status="DRAFT", commitment_grade=prior.commitment_grade,
        effective_from=effective_from, evidence_source=prior.evidence_source,
        evidence_start=prior.evidence_start, evidence_end=prior.evidence_end,
        calculation_method=prior.calculation_method, evidence_count=prior.evidence_count,
        minimum_evidence_count=prior.minimum_evidence_count, owner=prior.owner,
        review_due_at=prior.review_due_at, supersedes_id=prior.id,
        evidence_schema_version=prior.evidence_schema_version,
        evidence=json.loads(prior.evidence_json),
    )
    values.update(changes)
    successor = await add_assumption(db, **values)
    await db.flush()
    return successor


def _dates_overlap(start_a: date, end_a: date | None,
                   start_b: date, end_b: date | None) -> bool:
    end_a = end_a or date.max
    end_b = end_b or date.max
    return start_a <= end_b and start_b <= end_a


async def add_capacity_version(db: AsyncSession, *, pool_id: int,
                               effective_from: date, effective_to: date | None = None,
                               status: str = "DRAFT", capacity_scope: str,
                               capacity_schedule: dict | None = None,
                               slot_count: int | None = None,
                               calendar_policy: dict | None = None,
                               external_policy: dict | None = None,
                               assumption_id: int | None = None) -> ResourceCapacityVersion:
    pool = await db.get(ResourcePool, pool_id)
    if pool is None:
        raise InvalidCapacityVersion("Resource pool not found")
    status = status.upper()
    capacity_scope = capacity_scope.upper()
    _require_choice(status, CAPACITY_STATUSES, "capacity status", InvalidCapacityVersion)
    _require_choice(capacity_scope, CAPACITY_SCOPES, "capacity scope", InvalidCapacityVersion)
    if effective_to is not None and effective_to < effective_from:
        raise InvalidCapacityVersion("effective_to must not precede effective_from")
    if pool.capacity_unit == "HOURS":
        if slot_count is not None:
            raise InvalidCapacityVersion("Hour pools cannot define slot count")
        if not capacity_schedule:
            raise InvalidCapacityVersion("Hour pools require a capacity schedule")
    else:
        if capacity_schedule:
            raise InvalidCapacityVersion("Slot pools cannot define hour schedules")
        if slot_count is None or slot_count < 1:
            raise InvalidCapacityVersion("Slot pools require a positive slot count")
    existing = (await db.execute(
        select(ResourceCapacityVersion).where(ResourceCapacityVersion.pool_id == pool_id)
    )).scalars().all()
    if any(_dates_overlap(effective_from, effective_to, row.effective_from, row.effective_to)
           for row in existing):
        raise CapacityVersionOverlap("Capacity effective ranges cannot overlap")
    row = ResourceCapacityVersion(
        pool_id=pool_id, effective_from=effective_from, effective_to=effective_to,
        status=status, capacity_scope=capacity_scope,
        capacity_schedule_json=(json.dumps(capacity_schedule, sort_keys=True)
                                if capacity_schedule else None),
        slot_count=slot_count,
        calendar_policy_json=json.dumps(calendar_policy or {}, sort_keys=True),
        external_policy_json=json.dumps(external_policy or {}, sort_keys=True),
        assumption_id=assumption_id,
    )
    db.add(row)
    await db.flush()
    return row


async def add_binding(db: AsyncSession, *, program: str, pool_id: int,
                      acquire_op: int, requirement_mode: str, quantity: float,
                      demand_source: str, release_event: str,
                      release_op: int | None = None, part_no: str | None = None,
                      routing_revision: str | None = None,
                      routing_alternative: str = "*", min_hold_hours: float = 0.0,
                      lag_hours: float = 0.0, instance_code: str | None = None,
                      assumption_id: int | None = None, status: str = "DRAFT",
                      valid_operations: set[int] | None = None) -> OperationResourceBinding:
    pool = await db.get(ResourcePool, pool_id)
    if pool is None:
        raise InvalidBinding("Resource pool not found")
    requirement_mode = requirement_mode.upper()
    demand_source = demand_source.upper()
    release_event = release_event.upper()
    status = status.upper()
    _require_choice(requirement_mode, REQUIREMENT_MODES, "requirement mode", InvalidBinding)
    _require_choice(demand_source, DEMAND_SOURCES, "demand source", InvalidBinding)
    _require_choice(release_event, RELEASE_EVENTS, "release event", InvalidBinding)
    _require_choice(status, CAPACITY_STATUSES, "binding status", InvalidBinding)
    if requirement_mode == "EFFORT" and pool.capacity_unit != "HOURS":
        raise InvalidBinding("Effort bindings require an HOURS pool")
    if requirement_mode == "OCCUPANCY" and pool.capacity_unit != "SLOTS":
        raise InvalidBinding("Occupancy bindings require a SLOTS pool")
    if quantity <= 0 or min_hold_hours < 0 or lag_hours < 0:
        raise InvalidBinding("Binding quantities and hold times must be non-negative")
    if status == "APPROVED":
        if not valid_operations or acquire_op not in valid_operations:
            raise InvalidBinding("Approved binding acquire operation is not in the routing")
        if requirement_mode == "OCCUPANCY" and release_event in {"OP_START", "OP_COMPLETE"}:
            if release_op is None or release_op not in valid_operations:
                raise InvalidBinding("Approved binding release operation is not in the routing")
    row = OperationResourceBinding(
        program=program.upper(), part_no=part_no, routing_revision=routing_revision,
        routing_alternative=routing_alternative, pool_id=pool_id,
        acquire_op=acquire_op, release_op=release_op,
        requirement_mode=requirement_mode, quantity=quantity,
        demand_source=demand_source, release_event=release_event,
        min_hold_hours=min_hold_hours, lag_hours=lag_hours,
        instance_code=instance_code, assumption_id=assumption_id, status=status,
    )
    db.add(row)
    await db.flush()
    return row


async def define_physical_labor_pool(
        db: AsyncSession, *, code: str, site: str, name: str,
        bindings: dict[str, set[int]], shift_capacity: dict[int, float],
        weekday_factors: dict[int, float], calendar_exceptions: dict,
        calendar_covered_until: date, effective_from: date,
        owner: str, approver: str, evidence_source: str,
        calculation_method: str, review_due_at: date,
        capacity_scope: str = "GROSS_SITE",
        external_reserve: dict[int, float] | None = None,
        commitment_grade: str = "INTERNAL_ONLY",
        work_center_no: str | None = None) -> dict:
    """Create one reviewed physical labor pool and replace covered effort bindings.

    This is intentionally create-only. Any later value change must use assumption and capacity
    successors, preserving the exact inputs used by earlier shadow forecasts.
    """
    from app.engines.router_registry import registry

    required_text = (code, site, name, owner, approver, evidence_source, calculation_method)
    if not all((value or "").strip() for value in required_text):
        raise ResourceRegistryError(
            "Physical labor pools require identity, ownership, and evidence details")
    _require_choice(
        commitment_grade.upper(), COMMITMENT_GRADES,
        "commitment grade", ResourceRegistryError)
    if not bindings:
        raise ResourceRegistryError("Physical labor pools require operation bindings")
    if set(weekday_factors) != set(range(7)):
        raise ResourceRegistryError("Physical labor pools require weekday factors 0 through 6")
    if (not shift_capacity
            or any(float(value) < 0 for value in shift_capacity.values())):
        raise ResourceRegistryError("Shift capacity cannot be negative")
    if any(float(value) < 0 for value in weekday_factors.values()):
        raise ResourceRegistryError("Weekday factors cannot be negative")
    if any(float(value) < 0 for value in calendar_exceptions.values()):
        raise ResourceRegistryError("Calendar exception factors cannot be negative")
    if calendar_covered_until < effective_from:
        raise ResourceRegistryError("Calendar coverage cannot precede the effective date")
    if review_due_at < effective_from:
        raise ResourceRegistryError("Review date cannot precede the effective date")
    capacity_scope = capacity_scope.upper()
    if capacity_scope == "GROSS_SITE":
        if external_reserve is None:
            raise ResourceRegistryError(
                "Gross-site capacity requires an explicit external reserve")
        missing_shifts = set(shift_capacity) - set(external_reserve)
        if missing_shifts or any(float(value) < 0 for value in external_reserve.values()):
            raise ResourceRegistryError(
                "External reserve must provide non-negative hours for every capacity shift")
    elif capacity_scope != "NET_TRACKED":
        raise ResourceRegistryError(f"Invalid capacity scope: {capacity_scope}")

    normalized_bindings = {}
    for program, operation_numbers in bindings.items():
        program = program.upper()
        valid_operations = {int(row[0]) for row in registry.ops(program)}
        requested = {int(opno) for opno in operation_numbers}
        unknown = requested - valid_operations
        if unknown:
            raise InvalidBinding(
                f"{program} physical pool binding has unknown operations: {sorted(unknown)}")
        normalized_bindings[program] = (requested, valid_operations)

    existing = await db.scalar(select(ResourcePool).where(ResourcePool.code == code.strip()))
    if existing is not None:
        raise ResourceRegistryError(
            "Physical pool codes are immutable; supersede its assumptions and capacity version")
    pool = await create_pool(
        db, code=code, site=site, name=name, resource_type="LABOR",
        capacity_unit="HOURS", work_center_no=work_center_no,
    )
    capacity_assumption = await add_assumption(
        db, subject_type="POOL", subject_key=pool.code, parameter="shift_capacity",
        value={str(key): float(value) for key, value in shift_capacity.items()},
        unit="HOURS_PER_SHIFT", basis="OWNER_CONFIRMED",
        approval_status="APPROVED", commitment_grade=commitment_grade,
        effective_from=effective_from, evidence_source=evidence_source,
        calculation_method=calculation_method, owner=owner, approver=approver,
        review_due_at=review_due_at,
    )
    external_policy = {"mode": "INCLUDED_IN_NET"}
    reserve_assumption = None
    if capacity_scope == "GROSS_SITE":
        reserve_assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code,
            parameter="external_reserve",
            value={str(key): float(value) for key, value in external_reserve.items()},
            unit="HOURS_PER_SHIFT", basis="OWNER_CONFIRMED",
            approval_status="APPROVED", commitment_grade=commitment_grade,
            effective_from=effective_from, evidence_source=evidence_source,
            calculation_method=calculation_method, owner=owner, approver=approver,
            review_due_at=review_due_at,
        )
        external_policy = {
            "mode": "STATIC_RESERVE",
            "shift_reserve": {
                str(key): float(value) for key, value in external_reserve.items()
            },
            "assumption_id": reserve_assumption.id,
        }
    capacity = await add_capacity_version(
        db, pool_id=pool.id, effective_from=effective_from, status="APPROVED",
        capacity_scope=capacity_scope,
        capacity_schedule={str(key): float(value) for key, value in shift_capacity.items()},
        calendar_policy={
            "mode": "WEEKDAY_FACTORS",
            "factors": {str(key): float(value) for key, value in weekday_factors.items()},
            "exceptions": {
                (key.isoformat() if isinstance(key, date) else str(key)): float(value)
                for key, value in calendar_exceptions.items()
            },
            "covered_until": calendar_covered_until.isoformat(),
        },
        external_policy=external_policy, assumption_id=capacity_assumption.id,
    )
    created_bindings = []
    for program, (requested, valid_operations) in sorted(normalized_bindings.items()):
        prior_rows = (await db.execute(select(OperationResourceBinding).where(
            OperationResourceBinding.program == program,
            OperationResourceBinding.acquire_op.in_(requested),
            OperationResourceBinding.requirement_mode == "EFFORT",
            OperationResourceBinding.status == "APPROVED",
        ))).scalars().all()
        for prior in prior_rows:
            prior.status = "SUPERSEDED"
        for opno in sorted(requested):
            created_bindings.append(await add_binding(
                db, program=program, pool_id=pool.id, acquire_op=opno,
                requirement_mode="EFFORT", quantity=1.0, demand_source="LABOR",
                release_event="OP_COMPLETE", status="APPROVED",
                valid_operations=valid_operations,
            ))
    await db.flush()
    return {
        "pool": pool,
        "capacity": capacity,
        "capacity_assumption": capacity_assumption,
        "reserve_assumption": reserve_assumption,
        "bindings": tuple(created_bindings),
    }


async def capacity_policy_coverage(db: AsyncSession, pool: ResourcePool,
                                   version: ResourceCapacityVersion,
                                   as_of: date) -> list[CoverageIssue]:
    """Validate the calendar and external-reserve contract for one physical pool."""
    if pool.capacity_unit != "HOURS" or pool.code.startswith("LEGACY:"):
        return []
    issues = []
    calendar_policy = json.loads(version.calendar_policy_json or "{}")
    calendar_factors = (calendar_policy.get("factors")
                        if isinstance(calendar_policy, dict) else None)
    calendar_exceptions = (calendar_policy.get("exceptions")
                           if isinstance(calendar_policy, dict) else None)
    covered_until = (calendar_policy.get("covered_until")
                     if isinstance(calendar_policy, dict) else None)
    covered_until_date = _policy_date(covered_until)
    if (not isinstance(calendar_policy, dict)
            or calendar_policy.get("mode") != "WEEKDAY_FACTORS"
            or not isinstance(calendar_factors, dict)
            or any(str(day) not in calendar_factors for day in range(7))
            or not isinstance(calendar_exceptions, dict)
            or covered_until_date is None):
        issues.append(CoverageIssue(
            pool.code, "calendar_policy", "MISSING",
            "Physical labor pools require factors, exceptions, and a coverage end",
        ))
    elif covered_until_date < as_of:
        issues.append(CoverageIssue(
            pool.code, "calendar_policy", "MISSING",
            "Physical labor-pool calendar does not cover this date",
        ))
    if version.capacity_scope != "GROSS_SITE":
        return issues
    external_policy = json.loads(version.external_policy_json or "{}")
    policy_mode = (external_policy.get("mode")
                   if isinstance(external_policy, dict) else None)
    if policy_mode == "STATIC_RESERVE":
        shift_reserve = external_policy.get("shift_reserve") or {}
        capacity_schedule = json.loads(version.capacity_schedule_json or "{}")
        if (not isinstance(shift_reserve, dict)
                or any(str(shift) not in shift_reserve for shift in capacity_schedule)
                or any(float(value) < 0 for value in shift_reserve.values())):
            issues.append(CoverageIssue(
                pool.code, "external_reserve", "MISSING",
                "Static reserve must provide non-negative hours for each capacity shift",
            ))
            return issues
        reserve_id = external_policy.get("assumption_id")
        reserve_assumption = (await db.get(ModelAssumption, int(reserve_id))
                              if reserve_id else None)
        if (reserve_assumption is None
                or reserve_assumption.approval_status != "APPROVED"):
            issues.append(CoverageIssue(
                pool.code, "external_reserve", "MISSING",
                "Static external reserve requires an approved assumption",
            ))
        elif (reserve_assumption.commitment_grade == "INTERNAL_ONLY"
              or (reserve_assumption.review_due_at
                  and reserve_assumption.review_due_at < as_of)):
            issues.append(CoverageIssue(
                pool.code, "external_reserve", "PROVISIONAL",
                "Static external reserve is internal-only or past review",
            ))
    elif policy_mode == "SNAPSHOT":
        issues.append(CoverageIssue(
            pool.code, "external_reserve", "MISSING",
            "Dynamic external reserve allocation remains gated to BCA-03c",
        ))
    else:
        issues.append(CoverageIssue(
            pool.code, "external_reserve", "MISSING",
            "Gross-site capacity requires an explicit external reserve policy",
        ))
    return issues


async def resource_coverage(db: AsyncSession, program: str,
                            as_of: date) -> list[CoverageIssue]:
    bindings = (await db.execute(
        select(OperationResourceBinding).where(
            OperationResourceBinding.program == program.upper(),
            OperationResourceBinding.status == "APPROVED",
        )
    )).scalars().all()
    issues: list[CoverageIssue] = []
    try:
        from app.engines.router_registry import registry

        bound_ops = {
            binding.acquire_op for binding in bindings
            if binding.requirement_mode == "EFFORT"
        }
        missing_by_wc = {}
        for opno, _description, wc, _hours, _milestone in registry.ops(program.upper()):
            if int(opno) not in bound_ops:
                missing_by_wc.setdefault(wc or "UNMAPPED", []).append(int(opno))
        for wc, operations in sorted(missing_by_wc.items()):
            issues.append(CoverageIssue(
                wc, "resource_binding", "MISSING",
                "No approved resource binding for operations "
                + ", ".join(str(opno) for opno in operations),
            ))
    except KeyError:
        pass
    for pool_id in sorted({binding.pool_id for binding in bindings}):
        pool = await db.get(ResourcePool, pool_id)
        if pool is None:
            continue
        versions = (await db.execute(
            select(ResourceCapacityVersion).where(
                ResourceCapacityVersion.pool_id == pool_id,
                ResourceCapacityVersion.status == "APPROVED",
                ResourceCapacityVersion.effective_from <= as_of,
            )
        )).scalars().all()
        version = next((row for row in versions
                        if row.effective_to is None or row.effective_to >= as_of), None)
        if pool.retired_at is not None and pool.retired_at.date() <= as_of:
            version = None
        if version is None:
            issues.append(CoverageIssue(pool.code, "capacity", "MISSING",
                                        "No approved capacity version covers this date"))
            continue
        assumption = (await db.get(ModelAssumption, version.assumption_id)
                      if version.assumption_id else None)
        if assumption is None or assumption.approval_status != "APPROVED":
            issues.append(CoverageIssue(pool.code, "capacity", "MISSING",
                                        "Capacity has no approved assumption"))
            continue
        reasons = []
        if assumption.commitment_grade == "INTERNAL_ONLY":
            reasons.append("internal only")
        if assumption.review_due_at is not None and assumption.review_due_at < as_of:
            reasons.append("stale")
        if assumption.approval_status == "UNDER_REVIEW":
            reasons.append("under review")
        review_types = (await db.execute(
            select(AssumptionReview.review_type).where(
                AssumptionReview.assumption_id == assumption.id,
                AssumptionReview.status == "OPEN",
            )
        )).scalars().all()
        if review_types:
            reasons.append("open review: " + ", ".join(sorted(set(review_types))))
        if reasons:
            issues.append(CoverageIssue(pool.code, assumption.parameter, "PROVISIONAL",
                                        ", ".join(reasons)))
        issues.extend(await capacity_policy_coverage(db, pool, version, as_of))
    return issues
