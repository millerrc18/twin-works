"""Append-only quarantine for inconsistent source observations."""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ObservationQuarantineEvent


OPEN_EVENTS = {"OPEN", "REOPEN"}


@dataclass(frozen=True)
class QuarantineReconciliation:
    opened: int
    reopened: int
    resolved: int
    active: tuple[ObservationQuarantineEvent, ...]


def _canonical_json(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )


def quarantine_key(stream_key: str, order_no: str, reason_code: str) -> str:
    return f"{stream_key.upper()}:{order_no}:{reason_code}"[:160]


async def _latest_events(db: AsyncSession, stream_key: str) -> dict[str, ObservationQuarantineEvent]:
    latest_sequence = (
        select(
            ObservationQuarantineEvent.quarantine_key,
            func.max(ObservationQuarantineEvent.sequence).label("sequence"),
        )
        .where(ObservationQuarantineEvent.stream_key == stream_key.upper())
        .group_by(ObservationQuarantineEvent.quarantine_key)
        .subquery()
    )
    rows = (await db.execute(
        select(ObservationQuarantineEvent)
        .join(latest_sequence, (
            ObservationQuarantineEvent.quarantine_key == latest_sequence.c.quarantine_key
        ) & (ObservationQuarantineEvent.sequence == latest_sequence.c.sequence))
    )).scalars().all()
    return {row.quarantine_key: row for row in rows}


async def active_quarantines(db: AsyncSession, stream_key: str) -> list[ObservationQuarantineEvent]:
    latest = await _latest_events(db, stream_key)
    return sorted(
        (row for row in latest.values() if row.event_type in OPEN_EVENTS),
        key=lambda row: row.order_no,
    )


async def reconcile_quarantines(
        db: AsyncSession, *, stream_key: str, project_id: str, part_no: str,
        reason_code: str, conflicts: list[dict], actor: str) -> QuarantineReconciliation:
    """Append OPEN/REOPEN/RESOLVE events to match the current source conflicts."""
    stream_key = stream_key.upper()
    latest = await _latest_events(db, stream_key)
    current_keys = set()
    opened = reopened = resolved = 0
    for conflict in sorted(conflicts, key=lambda item: str(item["so"])):
        order_no = str(conflict["so"])
        key = quarantine_key(stream_key, order_no, reason_code)
        current_keys.add(key)
        prior = latest.get(key)
        if prior is not None and prior.event_type in OPEN_EVENTS:
            continue
        sequence = 1 if prior is None else prior.sequence + 1
        event_type = "OPEN" if prior is None else "REOPEN"
        row = ObservationQuarantineEvent(
            event_key=f"{key}:{sequence}:{event_type}", quarantine_key=key,
            sequence=sequence, stream_key=stream_key, project_id=project_id,
            part_no=part_no, order_no=order_no, serial=conflict.get("serial"),
            reason_code=reason_code, event_type=event_type, actor=actor,
            evidence_json=_canonical_json(conflict),
        )
        db.add(row)
        latest[key] = row
        opened += int(event_type == "OPEN")
        reopened += int(event_type == "REOPEN")
    for key, prior in sorted(latest.items()):
        if prior.event_type not in OPEN_EVENTS or key in current_keys:
            continue
        row = ObservationQuarantineEvent(
            event_key=f"{key}:{prior.sequence + 1}:RESOLVE", quarantine_key=key,
            sequence=prior.sequence + 1, stream_key=stream_key,
            project_id=prior.project_id, part_no=prior.part_no,
            order_no=prior.order_no, serial=prior.serial,
            reason_code=prior.reason_code, event_type="RESOLVE", actor=actor,
            evidence_json=_canonical_json({
                "resolution": "Source no longer meets quarantine rule",
                "prior_event_key": prior.event_key,
            }),
        )
        db.add(row)
        latest[key] = row
        resolved += 1
    await db.flush()
    active = tuple(sorted(
        (row for row in latest.values() if row.event_type in OPEN_EVENTS),
        key=lambda row: row.order_no,
    ))
    return QuarantineReconciliation(
        opened=opened, reopened=reopened, resolved=resolved, active=active)


def exclude_quarantined_orders(rows: list[dict], quarantines) -> list[dict]:
    excluded = {str(item.order_no) for item in quarantines}
    return [row for row in rows if str(row.get("order_no") or row.get("so")) not in excluded]
