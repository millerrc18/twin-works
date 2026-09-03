"""Append-only resource availability events and deterministic pooled-count folding."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ResourceAvailabilityEvent,
    ResourceCapacityVersion,
    ResourceInstance,
    ResourcePool,
)


EVENT_TYPES = {"OUTAGE_OPEN", "RETURN_TO_SERVICE", "EXTEND", "CANCEL", "VOID"}
REASON_CODES = {"TOOL_SHOP", "MAINTENANCE", "REPAIR", "CALIBRATION", "OTHER"}
AUTHORITY_ROLES = {"DATA_ADMIN", "PROGRAM_OWNER"}
CLOSED_EVENTS = {"RETURN_TO_SERVICE", "CANCEL", "VOID"}
UTC = timezone.utc


class AvailabilityEventError(ValueError):
    pass


class AvailabilityCapacityConflict(AvailabilityEventError):
    pass


@dataclass(frozen=True)
class OutageInterval:
    outage_key: str
    pool_id: int
    instance_code: str | None
    unavailable_quantity: int
    start: datetime
    end: datetime
    reason_code: str
    reason: str


@dataclass(frozen=True)
class PooledAvailabilityInterval:
    pool_id: int
    start: datetime
    end: datetime
    baseline_count: int
    unavailable_quantity: int
    available_count: int
    outage_keys: tuple[str, ...]


def _required_text(value: str | None, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AvailabilityEventError(f"{field} is required")
    return text


def _choice(value: str, allowed: set[str], field: str) -> str:
    normalized = _required_text(value, field).upper()
    if normalized not in allowed:
        raise AvailabilityEventError(f"Invalid {field}: {normalized}")
    return normalized


def _storage_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AvailabilityEventError(f"{field} must be a timezone-aware UTC datetime")
    normalized = value.astimezone(UTC)
    if value.utcoffset().total_seconds() != 0:
        raise AvailabilityEventError(f"{field} must be expressed in UTC")
    return normalized.replace(tzinfo=None)


def _read_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_evidence(value: dict) -> str:
    if not isinstance(value, dict) or not value:
        raise AvailabilityEventError("evidence must be a non-empty JSON object")
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AvailabilityEventError("evidence must contain deterministic JSON values") from exc


def _event_key(outage_key: str, sequence: int, event_type: str) -> str:
    return f"{outage_key}:{sequence}:{event_type}"[:180]


async def _pool_and_baseline(
        db: AsyncSession, pool_id: int, effective_at: datetime) -> tuple[ResourcePool, int]:
    pool = await db.get(ResourcePool, pool_id)
    if pool is None:
        raise AvailabilityEventError("Resource pool not found")
    if pool.resource_type != "TOOL" or pool.capacity_unit != "SLOTS":
        raise AvailabilityEventError("Phase 1 availability events require a TOOL/SLOTS pool")
    effective_date = _read_utc(effective_at).date()
    versions = (await db.execute(select(ResourceCapacityVersion).where(
        ResourceCapacityVersion.pool_id == pool.id,
        ResourceCapacityVersion.effective_from <= effective_date,
    ).order_by(
        ResourceCapacityVersion.effective_from.desc(),
        ResourceCapacityVersion.id.desc(),
    ))).scalars().all()
    version = next(
        (row for row in versions
         if row.effective_to is None or row.effective_to >= effective_date),
        None,
    )
    if version is None or version.slot_count is None:
        raise AvailabilityEventError("No slot-count version covers the outage start")
    return pool, int(version.slot_count)


async def _validate_instance(
        db: AsyncSession, pool_id: int, instance_code: str | None,
        unavailable_quantity: int) -> str | None:
    if instance_code is None:
        return None
    instance_code = _required_text(instance_code, "instance_code")
    if unavailable_quantity != 1:
        raise AvailabilityEventError("An instance outage must have unavailable quantity 1")
    instance = await db.scalar(select(ResourceInstance).where(
        ResourceInstance.pool_id == pool_id,
        ResourceInstance.instance_code == instance_code,
        ResourceInstance.active.is_(True),
    ))
    if instance is None:
        raise AvailabilityEventError("Resource instance not found or inactive")
    return instance_code


async def list_availability_events(
        db: AsyncSession, *, pool_id: int | None = None,
        outage_key: str | None = None) -> list[ResourceAvailabilityEvent]:
    query = select(ResourceAvailabilityEvent)
    if pool_id is not None:
        query = query.where(ResourceAvailabilityEvent.pool_id == pool_id)
    if outage_key is not None:
        query = query.where(ResourceAvailabilityEvent.outage_key == outage_key)
    query = query.order_by(
        ResourceAvailabilityEvent.pool_id,
        ResourceAvailabilityEvent.outage_key,
        ResourceAvailabilityEvent.sequence,
    )
    return list((await db.execute(query)).scalars().all())


def fold_outage(events: list[ResourceAvailabilityEvent]) -> OutageInterval | None:
    if not events:
        raise AvailabilityEventError("Outage event stream is empty")
    rows = sorted(events, key=lambda row: row.sequence)
    first = rows[0]
    if first.sequence != 1 or first.event_type != "OUTAGE_OPEN":
        raise AvailabilityEventError("Outage must begin with OUTAGE_OPEN sequence 1")
    if [row.sequence for row in rows] != list(range(1, len(rows) + 1)):
        raise AvailabilityEventError("Outage event sequence is not contiguous")
    start = _read_utc(first.effective_at)
    end = _read_utc(first.expected_end_at)
    if start is None or end is None or end <= start:
        raise AvailabilityEventError("Outage open interval is invalid")
    for row in rows[1:]:
        if (row.pool_id != first.pool_id
                or row.instance_code != first.instance_code
                or row.unavailable_quantity != first.unavailable_quantity):
            raise AvailabilityEventError("Outage event identity changed")
        if row.event_type == "EXTEND":
            candidate = _read_utc(row.expected_end_at)
            if candidate is None or candidate <= end:
                raise AvailabilityEventError("Extension must end after the current end")
            end = candidate
        elif row.event_type == "RETURN_TO_SERVICE":
            returned = _read_utc(row.effective_at)
            if returned is None or returned <= start:
                raise AvailabilityEventError("Return to service must follow the outage start")
            end = returned
            if row is not rows[-1]:
                raise AvailabilityEventError("Outage is closed and cannot accept later events")
        elif row.event_type == "CANCEL":
            occurred = _read_utc(row.occurred_at)
            if occurred is None or occurred > start:
                raise AvailabilityEventError("A started outage cannot be cancelled")
            if row is not rows[-1]:
                raise AvailabilityEventError("Outage is closed and cannot accept later events")
            return None
        elif row.event_type == "VOID":
            if row is not rows[-1]:
                raise AvailabilityEventError("Outage is closed and cannot accept later events")
            return None
        else:
            raise AvailabilityEventError(f"Invalid outage transition: {row.event_type}")
    return OutageInterval(
        outage_key=first.outage_key,
        pool_id=first.pool_id,
        instance_code=first.instance_code,
        unavailable_quantity=first.unavailable_quantity,
        start=start,
        end=end,
        reason_code=first.reason_code,
        reason=first.reason,
    )


def fold_pool_availability(
        events: list[ResourceAvailabilityEvent], *,
        baseline_count: int) -> tuple[PooledAvailabilityInterval, ...]:
    if isinstance(baseline_count, bool) or int(baseline_count) < 1:
        raise AvailabilityEventError("baseline_count must be a positive integer")
    baseline_count = int(baseline_count)
    grouped: dict[str, list[ResourceAvailabilityEvent]] = defaultdict(list)
    for event in events:
        grouped[event.outage_key].append(event)
    outages = [fold_outage(rows) for _key, rows in sorted(grouped.items())]
    outages = [row for row in outages if row is not None]
    if not outages:
        return tuple()
    pool_ids = {row.pool_id for row in outages}
    if len(pool_ids) != 1:
        raise AvailabilityEventError("A pooled timeline cannot mix resource pools")
    pool_id = next(iter(pool_ids))
    boundaries = sorted({point for row in outages for point in (row.start, row.end)})
    result = []
    for start, end in zip(boundaries, boundaries[1:]):
        active = sorted(
            (row for row in outages if row.start <= start < row.end),
            key=lambda row: row.outage_key,
        )
        unavailable = sum(row.unavailable_quantity for row in active)
        if unavailable == 0:
            continue
        if unavailable > baseline_count:
            raise AvailabilityCapacityConflict(
                f"Unavailable quantity {unavailable} exceeds baseline {baseline_count}")
        outage_keys = tuple(row.outage_key for row in active)
        segment = PooledAvailabilityInterval(
            pool_id=pool_id, start=start, end=end,
            baseline_count=baseline_count,
            unavailable_quantity=unavailable,
            available_count=baseline_count - unavailable,
            outage_keys=outage_keys,
        )
        if (result and result[-1].end == segment.start
                and result[-1].unavailable_quantity == segment.unavailable_quantity
                and result[-1].outage_keys == segment.outage_keys):
            prior = result[-1]
            result[-1] = PooledAvailabilityInterval(
                pool_id=prior.pool_id, start=prior.start, end=segment.end,
                baseline_count=prior.baseline_count,
                unavailable_quantity=prior.unavailable_quantity,
                available_count=prior.available_count,
                outage_keys=prior.outage_keys,
            )
        else:
            result.append(segment)
    return tuple(result)


async def _validate_prospective_pool_event(
        db: AsyncSession, event: ResourceAvailabilityEvent,
        *, baseline_at: datetime) -> None:
    _pool, baseline = await _pool_and_baseline(db, event.pool_id, baseline_at)
    existing = await list_availability_events(db, pool_id=event.pool_id)
    fold_pool_availability([*existing, event], baseline_count=baseline)


async def _latest_outage(
        db: AsyncSession, outage_key: str) -> list[ResourceAvailabilityEvent]:
    outage_key = _required_text(outage_key, "outage_key")
    rows = await list_availability_events(db, outage_key=outage_key)
    if not rows:
        raise AvailabilityEventError("Outage not found")
    return rows


async def _append_event(
        db: AsyncSession, *, prior: list[ResourceAvailabilityEvent],
        event_type: str, reason: str, actor: str, authority_role: str,
        evidence: dict, effective_at: datetime | None = None,
        expected_end_at: datetime | None = None,
        occurred_at: datetime | None = None) -> ResourceAvailabilityEvent:
    first = prior[0]
    if prior[-1].event_type in CLOSED_EVENTS:
        raise AvailabilityEventError("Outage is closed")
    event_type = _choice(event_type, EVENT_TYPES, "event_type")
    actor = _required_text(actor, "actor")
    authority_role = _choice(authority_role, AUTHORITY_ROLES, "authority_role")
    reason = _required_text(reason, "reason")
    occurred = _storage_utc(occurred_at or datetime.now(UTC), "occurred_at")
    effective = (_storage_utc(effective_at, "effective_at")
                 if effective_at is not None else None)
    expected = (_storage_utc(expected_end_at, "expected_end_at")
                if expected_end_at is not None else None)
    row = ResourceAvailabilityEvent(
        event_key=_event_key(first.outage_key, len(prior) + 1, event_type),
        outage_key=first.outage_key,
        sequence=len(prior) + 1,
        pool_id=first.pool_id,
        instance_code=first.instance_code,
        event_type=event_type,
        unavailable_quantity=first.unavailable_quantity,
        effective_at=effective,
        expected_end_at=expected,
        reason_code=first.reason_code,
        reason=reason,
        actor=actor,
        authority_role=authority_role,
        evidence_json=_canonical_evidence(evidence),
        occurred_at=occurred,
    )
    first_effective = _read_utc(first.effective_at)
    await _validate_prospective_pool_event(
        db, row, baseline_at=first_effective)
    db.add(row)
    await db.flush()
    return row


async def open_outage(
        db: AsyncSession, *, pool_id: int, unavailable_quantity: int,
        effective_at: datetime, expected_end_at: datetime,
        reason_code: str, reason: str, actor: str, authority_role: str,
        evidence: dict, instance_code: str | None = None,
        outage_key: str | None = None,
        occurred_at: datetime | None = None) -> ResourceAvailabilityEvent:
    effective = _storage_utc(effective_at, "effective_at")
    expected = _storage_utc(expected_end_at, "expected_end_at")
    if expected <= effective:
        raise AvailabilityEventError("expected_end_at must follow effective_at")
    if isinstance(unavailable_quantity, bool) or int(unavailable_quantity) < 1:
        raise AvailabilityEventError("unavailable_quantity must be a positive integer")
    unavailable_quantity = int(unavailable_quantity)
    pool, baseline = await _pool_and_baseline(db, pool_id, effective)
    if unavailable_quantity > baseline:
        raise AvailabilityEventError("unavailable_quantity exceeds the effective baseline")
    instance_code = await _validate_instance(
        db, pool.id, instance_code, unavailable_quantity)
    reason_code = _choice(reason_code, REASON_CODES, "reason_code")
    authority_role = _choice(authority_role, AUTHORITY_ROLES, "authority_role")
    actor = _required_text(actor, "actor")
    reason = _required_text(reason, "reason")
    occurred = _storage_utc(occurred_at or datetime.now(UTC), "occurred_at")
    key = _required_text(
        outage_key or f"AVAIL:{pool.code}:{uuid4().hex}", "outage_key")[:160]
    existing = await db.scalar(select(ResourceAvailabilityEvent.id).where(
        ResourceAvailabilityEvent.outage_key == key))
    if existing is not None:
        raise AvailabilityEventError("outage_key already exists")
    row = ResourceAvailabilityEvent(
        event_key=_event_key(key, 1, "OUTAGE_OPEN"),
        outage_key=key,
        sequence=1,
        pool_id=pool.id,
        instance_code=instance_code,
        event_type="OUTAGE_OPEN",
        unavailable_quantity=unavailable_quantity,
        effective_at=effective,
        expected_end_at=expected,
        reason_code=reason_code,
        reason=reason,
        actor=actor,
        authority_role=authority_role,
        evidence_json=_canonical_evidence(evidence),
        occurred_at=occurred,
    )
    await _validate_prospective_pool_event(db, row, baseline_at=effective)
    db.add(row)
    await db.flush()
    return row


async def extend_outage(
        db: AsyncSession, *, outage_key: str, expected_end_at: datetime,
        reason: str, actor: str, authority_role: str, evidence: dict,
        occurred_at: datetime | None = None) -> ResourceAvailabilityEvent:
    prior = await _latest_outage(db, outage_key)
    if prior[-1].event_type in CLOSED_EVENTS:
        raise AvailabilityEventError("Outage is closed")
    state = fold_outage(prior)
    expected = _storage_utc(expected_end_at, "expected_end_at")
    if state is None or _read_utc(expected) <= state.end:
        raise AvailabilityEventError("Extension must end after the current end")
    return await _append_event(
        db, prior=prior, event_type="EXTEND", expected_end_at=expected_end_at,
        reason=reason, actor=actor, authority_role=authority_role,
        evidence=evidence, occurred_at=occurred_at,
    )


async def return_to_service(
        db: AsyncSession, *, outage_key: str, effective_at: datetime,
        reason: str, actor: str, authority_role: str, evidence: dict,
        occurred_at: datetime | None = None) -> ResourceAvailabilityEvent:
    prior = await _latest_outage(db, outage_key)
    if prior[-1].event_type in CLOSED_EVENTS:
        raise AvailabilityEventError("Outage is closed")
    state = fold_outage(prior)
    returned = _read_utc(_storage_utc(effective_at, "effective_at"))
    if state is None or returned <= state.start:
        raise AvailabilityEventError("Return to service must follow the outage start")
    return await _append_event(
        db, prior=prior, event_type="RETURN_TO_SERVICE", effective_at=effective_at,
        reason=reason, actor=actor, authority_role=authority_role,
        evidence=evidence, occurred_at=occurred_at,
    )


async def cancel_outage(
        db: AsyncSession, *, outage_key: str, reason: str,
        actor: str, authority_role: str, evidence: dict,
        occurred_at: datetime | None = None) -> ResourceAvailabilityEvent:
    prior = await _latest_outage(db, outage_key)
    if prior[-1].event_type in CLOSED_EVENTS:
        raise AvailabilityEventError("Outage is closed")
    state = fold_outage(prior)
    occurred = _read_utc(_storage_utc(
        occurred_at or datetime.now(UTC), "occurred_at"))
    if state is None or occurred > state.start:
        raise AvailabilityEventError("A started outage cannot be cancelled")
    return await _append_event(
        db, prior=prior, event_type="CANCEL",
        reason=reason, actor=actor, authority_role=authority_role,
        evidence=evidence, occurred_at=occurred_at,
    )

async def void_outage(
        db: AsyncSession, *, outage_key: str, reason: str,
        actor: str, authority_role: str, evidence: dict,
        occurred_at: datetime | None = None) -> ResourceAvailabilityEvent:
    """Append a retrospective correction when the recorded outage never occurred."""
    prior = await _latest_outage(db, outage_key)
    if prior[-1].event_type in CLOSED_EVENTS:
        raise AvailabilityEventError("Outage is closed")
    return await _append_event(
        db, prior=prior, event_type="VOID",
        reason=reason, actor=actor, authority_role=authority_role,
        evidence=evidence, occurred_at=occurred_at,
    )
