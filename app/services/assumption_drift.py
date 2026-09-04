"""Expiry, drift, and recertification workflow for model assumptions."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccuracySummaryLog,
    AssumptionReview,
    ModelAssumption,
    ResourceAvailabilityEvent,
    ResourceCapacityVersion,
)
from app.services.assumption_evidence import canonical_evidence
from app.services.resource_registry import (
    InvalidAssumption,
    add_capacity_version,
    supersede_assumption,
)


REVIEW_TYPES = {
    "EXPIRY", "MISSING_REVIEW_DATE", "MISSING_DRIFT_POLICY",
    "BACKFILL_ATTESTATION", "DRIFT", "SPARSE_EVIDENCE", "MANUAL",
}
REVIEW_RESOLUTIONS = {"RECERTIFIED", "SUPERSEDED", "DISMISSED"}
REVIEW_AUTHORITY_ROLES = {"DATA_ADMIN", "IE_FLOOR", "PROGRAM_SCHEDULING"}
AUDIT_RETENTION_POLICY = "PERMANENT_APPEND_ONLY"


class AssumptionReviewError(ValueError):
    pass


@dataclass(frozen=True)
class DriftObservation:
    assumption_id: int
    observed_value: float
    sample_count: int
    window_start: date
    window_end: date
    source_ref: str


@dataclass(frozen=True)
class ReviewReport:
    as_of: date
    scanned: int
    opened: int
    existing: int
    reviews: tuple[AssumptionReview, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _required_text(value: str | None, field: str) -> str:
    value = (value or "").strip()
    if not value:
        raise AssumptionReviewError(f"{field} is required")
    return value


def _canonical_json(value) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AssumptionReviewError("Review evidence must be deterministic JSON") from exc


def _numeric_assumption_value(assumption: ModelAssumption) -> float | None:
    value = json.loads(assumption.value_json)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        values = list(value.values())
        if values and all(isinstance(item, (int, float)) and not isinstance(item, bool)
                          for item in values):
            return float(sum(values))
    return None


def _observation_payload(observation: DriftObservation) -> dict:
    payload = asdict(observation)
    payload["window_start"] = observation.window_start.isoformat()
    payload["window_end"] = observation.window_end.isoformat()
    return payload


def _review_key(assumption: ModelAssumption, review_type: str, discriminator: str) -> str:
    return f"assumption:{assumption.id}:{review_type}:{discriminator}"[:160]


async def _ensure_review(db: AsyncSession, *, assumption: ModelAssumption,
                         review_type: str, discriminator: str, reason: str,
                         evidence: dict, opened_by: str) -> tuple[AssumptionReview, bool]:
    if review_type not in REVIEW_TYPES:
        raise AssumptionReviewError(f"Invalid review type: {review_type}")
    key = _review_key(assumption, review_type, discriminator)
    result = await db.execute(sqlite_insert(AssumptionReview).values(
        assumption_id=assumption.id, review_key=key, review_type=review_type,
        status="OPEN", reason=reason, evidence_json=_canonical_json(evidence),
        owner=assumption.owner, opened_by=_required_text(opened_by, "opened_by"),
        opened_at=_utcnow(),
    ).on_conflict_do_nothing(index_elements=["review_key"]))
    row = await db.scalar(select(AssumptionReview).where(
        AssumptionReview.review_key == key))
    return row, result.rowcount == 1


async def build_drift_report(db: AsyncSession, as_of: date, *,
                             observations: Iterable[DriftObservation] = (),
                             opened_by: str = "TwinWorks governance") -> ReviewReport:
    """Create idempotent review debt without changing approved values or epochs."""
    assumptions = (await db.execute(select(ModelAssumption).where(
        ModelAssumption.approval_status == "APPROVED",
        ModelAssumption.effective_from <= as_of,
    ))).scalars().all()
    active = [row for row in assumptions if row.effective_to is None or row.effective_to >= as_of]
    observation_by_id = {item.assumption_id: item for item in observations}
    reviews: list[AssumptionReview] = []
    opened = existing = 0

    async def register(assumption, review_type, discriminator, reason, evidence):
        nonlocal opened, existing
        row, was_created = await _ensure_review(
            db, assumption=assumption, review_type=review_type,
            discriminator=discriminator, reason=reason, evidence=evidence,
            opened_by=opened_by,
        )
        reviews.append(row)
        opened += int(was_created)
        existing += int(not was_created)

    for assumption in active:
        evidence = json.loads(assumption.evidence_json)
        if evidence.get("migration"):
            await register(
                assumption, "BACKFILL_ATTESTATION", str(evidence["migration"]),
                "Migrated evidence requires owner attestation",
                {"migration": evidence["migration"], "as_of": as_of.isoformat()},
            )
        if assumption.review_due_at is None:
            await register(
                assumption, "MISSING_REVIEW_DATE", "v1",
                "Approved assumption has no recertification date",
                {"as_of": as_of.isoformat(), "assumption_id": assumption.id},
            )
        elif assumption.review_due_at < as_of:
            await register(
                assumption, "EXPIRY", assumption.review_due_at.isoformat(),
                f"Review date {assumption.review_due_at.isoformat()} has passed",
                {"as_of": as_of.isoformat(),
                 "review_due_at": assumption.review_due_at.isoformat()},
            )

        if (assumption.minimum_evidence_count is not None
                and (assumption.evidence_count or 0) < assumption.minimum_evidence_count):
            await register(
                assumption, "SPARSE_EVIDENCE", "v1",
                "Evidence count is below the approved minimum",
                {"evidence_count": assumption.evidence_count or 0,
                 "minimum_evidence_count": assumption.minimum_evidence_count},
            )

        if assumption.basis == "MEASURED_ACTUAL" and not evidence.get("drift_policy"):
            await register(
                assumption, "MISSING_DRIFT_POLICY", "v1",
                "Measured-actual assumption has no approved drift threshold",
                {"as_of": as_of.isoformat(), "evidence_schema_version":
                 assumption.evidence_schema_version},
            )

        observation = observation_by_id.get(assumption.id)
        if observation is None:
            continue
        policy = evidence.get("drift_policy") or {}
        threshold = policy.get("relative_threshold")
        minimum_samples = int(policy.get("minimum_samples", 1))
        if threshold is None:
            continue
        if observation.sample_count < minimum_samples:
            await register(
                assumption, "SPARSE_EVIDENCE", observation.window_end.isoformat(),
                "Drift observation is below the policy minimum sample count",
                {"observation": _observation_payload(observation),
                 "minimum_samples": minimum_samples},
            )
            continue
        baseline = _numeric_assumption_value(assumption)
        if baseline is None:
            continue
        relative_change = (abs(observation.observed_value - baseline) / abs(baseline)
                           if baseline else float("inf"))
        if relative_change > float(threshold):
            await register(
                assumption, "DRIFT", observation.window_end.isoformat(),
                f"Observed value drifted {relative_change:.1%} from approved value",
                {"observation": _observation_payload(observation),
                 "approved_value": baseline,
                 "relative_change": relative_change, "threshold": float(threshold)},
            )
    return ReviewReport(
        as_of=as_of, scanned=len(active), opened=opened, existing=existing,
        reviews=tuple(reviews),
    )


async def resolve_review(db: AsyncSession, review_id: int, *, resolution: str,
                         actor: str, authority_role: str, notes: str,
                         effective_from: date | None = None,
                         review_due_at: date | None = None,
                         replacement_value=None,
                         evidence: dict | None = None) -> AssumptionReview:
    """Resolve once; recertification and replacement always create a successor version."""
    row = await db.get(AssumptionReview, review_id)
    if row is None:
        raise AssumptionReviewError("Assumption review not found")
    if row.status != "OPEN":
        raise AssumptionReviewError("Assumption review is already closed")
    resolution = resolution.upper()
    authority_role = authority_role.upper()
    if resolution not in REVIEW_RESOLUTIONS:
        raise AssumptionReviewError(f"Invalid review resolution: {resolution}")
    if authority_role not in REVIEW_AUTHORITY_ROLES:
        raise AssumptionReviewError(f"Invalid authority role: {authority_role}")
    actor = _required_text(actor, "actor")
    notes = _required_text(notes, "notes")

    successor = None
    if resolution != "DISMISSED":
        if effective_from is None or review_due_at is None:
            raise AssumptionReviewError(
                "Recertification requires effective_from and review_due_at")
        prior = await db.get(ModelAssumption, row.assumption_id)
        if prior is None:
            raise AssumptionReviewError("Reviewed assumption no longer exists")
        value = json.loads(prior.value_json)
        if resolution == "SUPERSEDED":
            if replacement_value is None:
                raise AssumptionReviewError("SUPERSEDED requires replacement_value")
            value = replacement_value
        successor_evidence = evidence or json.loads(prior.evidence_json)
        successor_evidence = dict(successor_evidence)
        successor_evidence["recertification"] = {
            "review_key": row.review_key,
            "resolution": resolution,
            "actor": actor,
            "authority_role": authority_role,
            "resolved_at": _utcnow().isoformat(),
        }
        canonical_evidence(
            successor_evidence, schema_version=prior.evidence_schema_version,
            require_complete=True,
        )
        linked_capacities = (await db.execute(select(ResourceCapacityVersion).where(
            ResourceCapacityVersion.assumption_id == prior.id,
            ResourceCapacityVersion.status == "APPROVED",
        ))).scalars().all()
        try:
            successor = await supersede_assumption(
                db, prior.id, value=value, effective_from=effective_from,
                approval_status="APPROVED", approver=actor,
                review_due_at=review_due_at, evidence=successor_evidence,
            )
            for capacity in linked_capacities:
                capacity.status = "SUPERSEDED"
                capacity.effective_to = effective_from - timedelta(days=1)
                schedule = (json.loads(capacity.capacity_schedule_json)
                            if capacity.capacity_schedule_json else None)
                slots = capacity.slot_count
                if resolution == "SUPERSEDED":
                    if schedule is not None and isinstance(value, dict):
                        schedule = value
                    elif slots is not None and isinstance(value, int):
                        slots = value
                await add_capacity_version(
                    db, pool_id=capacity.pool_id, effective_from=effective_from,
                    status="APPROVED", capacity_scope=capacity.capacity_scope,
                    capacity_schedule=schedule, slot_count=slots,
                    calendar_policy=json.loads(capacity.calendar_policy_json),
                    external_policy=json.loads(capacity.external_policy_json),
                    assumption_id=successor.id,
                )
        except InvalidAssumption as exc:
            raise AssumptionReviewError(str(exc)) from exc

    row.status = "DISMISSED" if resolution == "DISMISSED" else "RESOLVED"
    row.resolved_at = _utcnow()
    row.resolved_by = actor
    row.resolution = resolution
    row.successor_assumption_id = successor.id if successor else None
    row.resolution_notes = notes
    await db.flush()
    return row


async def export_assumption_audit(db: AsyncSession) -> dict:
    """Return deterministic, append-only governance history for external retention."""
    assumptions = (await db.execute(
        select(ModelAssumption).order_by(ModelAssumption.id)
    )).scalars().all()
    reviews = (await db.execute(
        select(AssumptionReview).order_by(AssumptionReview.id)
    )).scalars().all()
    capacities = (await db.execute(
        select(ResourceCapacityVersion).order_by(ResourceCapacityVersion.id)
    )).scalars().all()
    availability_events = (await db.execute(
        select(ResourceAvailabilityEvent).order_by(
            ResourceAvailabilityEvent.pool_id,
            ResourceAvailabilityEvent.outage_key,
            ResourceAvailabilityEvent.sequence,
        )
    )).scalars().all()
    accuracy_summaries = (await db.execute(
        select(AccuracySummaryLog).order_by(
            AccuracySummaryLog.as_of_date,
            AccuracySummaryLog.program,
            AccuracySummaryLog.horizon_days,
            AccuracySummaryLog.id,
        )
    )).scalars().all()
    return {
        "schema_version": 1,
        "retention_policy": AUDIT_RETENTION_POLICY,
        "exported_at": _utcnow().isoformat(),
        "assumptions": [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in assumptions
        ],
        "reviews": [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in reviews
        ],
        "capacity_versions": [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in capacities
        ],
        "availability_events": [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in availability_events
        ],
        "accuracy_summaries": [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in accuracy_summaries
        ],
    }
