"""RATE-01a governed baseline contexts and staffing evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelAssumption, ResourcePool
from app.services.resource_registry import add_assumption


SKILL_PARAMETER = "rate_staffing_model"


class RateGovernanceError(ValueError):
    """A rate baseline or staffing record cannot be governed safely."""


@dataclass(frozen=True)
class BaselineEpochRef:
    epoch_id: int
    epoch_key: str
    definition_hash: str
    lifecycle_state: str
    resource_mode: str


@dataclass(frozen=True)
class RateBaselineContext:
    baseline_kind: str
    snapshot_id: int
    content_hash: str
    readiness: str
    programs: tuple[str, ...]
    epochs: dict[str, BaselineEpochRef]


@dataclass(frozen=True)
class GovernedSkillEvidence:
    assumption_id: int
    skill_pool: str
    current_fte: Decimal
    productive_hours_per_fte: Decimal
    eligible_work_centers: tuple[str, ...]
    eligible_shifts: tuple[int, ...]
    learning_curve: tuple[Decimal, ...]
    retention_yield: Decimal
    effective_from: date
    effective_to: date | None
    review_due_at: date | None
    readiness: str
    readiness_reasons: tuple[str, ...]


def _decimal(value, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RateGovernanceError(f"{field} must be numeric") from None
    if not result.is_finite():
        raise RateGovernanceError(f"{field} must be finite")
    return result


async def build_rate_baseline_context(
        db: AsyncSession, *, programs: list[str], baseline_kind: str,
        as_of: datetime, horizon_end: date,
        epoch_ids: dict[str, int] | None = None) -> RateBaselineContext:
    """Persist one immutable published or candidate planning context."""
    from app.engines.router_registry import registry
    from app.services.model_epoch_service import resolve_epochs_for_run
    from app.services.resource_profile import compile_profile

    codes = tuple(dict.fromkeys(program.upper() for program in programs))
    if not codes or any(code not in registry.programs for code in codes):
        raise RateGovernanceError("rate context contains an inactive or unknown program")
    kind = baseline_kind.upper()
    if kind not in {"PUBLISHED", "CANDIDATE"}:
        raise RateGovernanceError("baseline_kind must be PUBLISHED or CANDIDATE")
    normalized_ids = ({key.upper(): value for key, value in epoch_ids.items()}
                      if epoch_ids else None)
    if kind == "CANDIDATE" and (normalized_ids is None or set(normalized_ids) != set(codes)):
        raise RateGovernanceError(
            "candidate epoch selection must cover exactly every selected program")
    if kind == "PUBLISHED" and normalized_ids is not None:
        raise RateGovernanceError("published context cannot accept explicit candidate epochs")
    try:
        selected = await resolve_epochs_for_run(
            db, codes, requested=normalized_ids)
    except Exception as exc:
        raise RateGovernanceError(str(exc)) from exc
    if kind == "CANDIDATE" and any(
            selection.epoch.epoch_kind != "CANDIDATE"
            for selection in selected.values()):
        raise RateGovernanceError("candidate context requires candidate epochs")
    modes = {selection.epoch.resource_mode for selection in selected.values()}
    if len(modes) != 1:
        raise RateGovernanceError(
            "selected epochs use mixed resource modes and cannot share one context")
    mode = next(iter(modes))
    compiled = await compile_profile(
        db,
        programs=list(codes),
        as_of=as_of,
        horizon_end=horizon_end,
        mode=mode,
        epoch_ids={program: selection.epoch.id
                   for program, selection in selected.items()},
    )
    refs = {
        program: BaselineEpochRef(
            epoch_id=selection.epoch.id,
            epoch_key=selection.epoch.epoch_key,
            definition_hash=selection.epoch.definition_hash,
            lifecycle_state=selection.state,
            resource_mode=selection.epoch.resource_mode,
        )
        for program, selection in selected.items()
    }
    return RateBaselineContext(
        baseline_kind=kind,
        snapshot_id=compiled.snapshot_id,
        content_hash=compiled.snapshot_hash,
        readiness=compiled.readiness,
        programs=codes,
        epochs=refs,
    )


def _validate_skill_payload(
        *, current_fte, productive_hours_per_fte,
        eligible_work_centers, eligible_shifts,
        learning_curve, retention_yield,
        effective_from, effective_to, review_due_at) -> dict:
    current = _decimal(current_fte, "current_fte")
    productive = _decimal(productive_hours_per_fte, "productive_hours_per_fte")
    retention = _decimal(retention_yield, "retention_yield")
    if current < 0 or productive <= 0:
        raise RateGovernanceError(
            "current_fte must be non-negative and productive hours must be positive")
    if retention <= 0 or retention > 1:
        raise RateGovernanceError("retention_yield must be greater than 0 and at most 1")
    work_centers = tuple(sorted({str(item).strip() for item in eligible_work_centers
                                 if str(item).strip()}))
    shifts = tuple(sorted({int(item) for item in eligible_shifts}))
    if not work_centers:
        raise RateGovernanceError("eligible_work_centers cannot be empty")
    if not shifts or any(shift not in {1, 2, 3} for shift in shifts):
        raise RateGovernanceError("eligible_shifts must use shifts 1, 2, or 3")
    curve = tuple(_decimal(item, "learning_curve") for item in learning_curve)
    if not curve or any(item <= 0 or item > 1 for item in curve):
        raise RateGovernanceError("learning_curve values must be greater than 0 and at most 1")
    if any(right < left for left, right in zip(curve, curve[1:])):
        raise RateGovernanceError("learning_curve must be nondecreasing")
    if effective_to is not None and effective_to < effective_from:
        raise RateGovernanceError("effective_to must not precede effective_from")
    if review_due_at < effective_from:
        raise RateGovernanceError("review_due_at must not precede effective_from")
    return {
        "current_fte": str(current),
        "productive_hours_per_fte": str(productive),
        "eligible_work_centers": list(work_centers),
        "eligible_shifts": list(shifts),
        "learning_curve": [str(item) for item in curve],
        "retention_yield": str(retention),
    }


async def record_skill_evidence(
        db: AsyncSession, *, pool_code: str, current_fte,
        productive_hours_per_fte, eligible_work_centers,
        eligible_shifts, learning_curve, retention_yield,
        effective_from: date, review_due_at: date,
        owner: str, approver: str | None, approval_status: str,
        evidence: dict, effective_to: date | None = None) -> ModelAssumption:
    """Append one effective-dated staffing model to a governed labor pool."""
    pool = await db.scalar(select(ResourcePool).where(ResourcePool.code == pool_code))
    if pool is None or pool.resource_type != "LABOR" or pool.capacity_unit != "HOURS":
        raise RateGovernanceError("rate staffing evidence requires a LABOR/HOURS pool")
    payload = _validate_skill_payload(
        current_fte=current_fte,
        productive_hours_per_fte=productive_hours_per_fte,
        eligible_work_centers=eligible_work_centers,
        eligible_shifts=eligible_shifts,
        learning_curve=learning_curve,
        retention_yield=retention_yield,
        effective_from=effective_from,
        effective_to=effective_to,
        review_due_at=review_due_at,
    )
    existing = (await db.execute(select(ModelAssumption).where(
        ModelAssumption.subject_type == "POOL",
        ModelAssumption.subject_key == pool.code,
        ModelAssumption.parameter == SKILL_PARAMETER,
    ))).scalars().all()
    new_end = effective_to or date.max
    if any(effective_from <= (row.effective_to or date.max)
           and row.effective_from <= new_end for row in existing):
        raise RateGovernanceError("rate staffing evidence effective ranges overlap")
    status = approval_status.upper()
    return await add_assumption(
        db,
        subject_type="POOL",
        subject_key=pool.code,
        parameter=SKILL_PARAMETER,
        value=payload,
        unit="RATE_STAFFING_MODEL_V1",
        basis="OWNER_CONFIRMED",
        approval_status=status,
        commitment_grade=("COMMITMENT_READY" if status == "APPROVED"
                          else "INTERNAL_ONLY"),
        effective_from=effective_from,
        effective_to=effective_to,
        evidence_source=(evidence.get("source_refs") or [None])[0],
        evidence_start=(date.fromisoformat(evidence["window"]["start"])
                        if evidence.get("window") else None),
        evidence_end=(date.fromisoformat(evidence["window"]["end"])
                      if evidence.get("window") else None),
        calculation_method=evidence.get("method"),
        evidence_count=evidence.get("sample_count"),
        minimum_evidence_count=(evidence.get("drift_policy") or {}).get("minimum_samples"),
        owner=owner,
        approver=approver,
        review_due_at=review_due_at,
        evidence=evidence,
    )


async def load_skill_evidence(
        db: AsyncSession, pool_code: str, *, as_of: date) -> GovernedSkillEvidence:
    row = await db.scalar(select(ModelAssumption).where(
        ModelAssumption.subject_type == "POOL",
        ModelAssumption.subject_key == pool_code,
        ModelAssumption.parameter == SKILL_PARAMETER,
        ModelAssumption.effective_from <= as_of,
        or_(ModelAssumption.effective_to.is_(None),
            ModelAssumption.effective_to >= as_of),
    ).order_by(ModelAssumption.effective_from.desc(), ModelAssumption.id.desc()).limit(1))
    if row is None:
        raise RateGovernanceError(f"no staffing evidence for {pool_code}")
    value = json.loads(row.value_json)
    reasons = []
    if row.approval_status != "APPROVED":
        reasons.append(row.approval_status)
    if row.commitment_grade != "COMMITMENT_READY":
        reasons.append("INTERNAL_ONLY")
    if row.review_due_at is not None and row.review_due_at < as_of:
        reasons.append("PAST_REVIEW")
    return GovernedSkillEvidence(
        assumption_id=row.id,
        skill_pool=pool_code,
        current_fte=Decimal(value["current_fte"]),
        productive_hours_per_fte=Decimal(value["productive_hours_per_fte"]),
        eligible_work_centers=tuple(value["eligible_work_centers"]),
        eligible_shifts=tuple(int(item) for item in value["eligible_shifts"]),
        learning_curve=tuple(Decimal(item) for item in value["learning_curve"]),
        retention_yield=Decimal(value["retention_yield"]),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        review_due_at=row.review_due_at,
        readiness=("READY" if not reasons else "PROVISIONAL"),
        readiness_reasons=tuple(reasons),
    )
