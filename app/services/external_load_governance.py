"""Immutable external-load snapshots and forecast-horizon readiness checks."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AssumptionReview,
    ExternalLoadRow,
    ExternalLoadSnapshot,
    ModelAssumption,
)
from app.services.resource_registry import CoverageIssue


BEYOND_HORIZON_POLICIES = {"BLOCK", "HOLD_LAST_COMPLETE_WEEK", "TRAILING_MEAN"}


@dataclass(frozen=True)
class ExternalSnapshotAssessment:
    snapshot_id: int
    payload: dict
    assumption_ids: tuple[int, ...]
    issues: tuple[CoverageIssue, ...]


def _canonical_json(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


def _normalized_timestamp(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="microseconds")


def _snapshot_payload(snapshot: ExternalLoadSnapshot, rows: list[ExternalLoadRow]) -> dict:
    return {
        "schema_version": snapshot.schema_version,
        "captured_at": _normalized_timestamp(snapshot.captured_at),
        "source": snapshot.source,
        "coverage_start": snapshot.coverage_start.isoformat(),
        "coverage_end": snapshot.coverage_end.isoformat(),
        "tracked_programs": sorted(json.loads(snapshot.tracked_programs_json)),
        "quality_policy": json.loads(snapshot.quality_policy_json),
        "assumption_ids": sorted(json.loads(snapshot.assumption_ids_json)),
        "rows": [
            {
                "pool_id": row.pool_id,
                "work_date": row.work_date.isoformat(),
                "shift": row.shift,
                "project_id": row.project_id,
                "order_no": row.order_no,
                "part_no": row.part_no,
                "source_type": row.source_type,
                "load_type": row.load_type,
                "hours": row.hours,
                "units": row.units,
                "quality": row.quality,
                "weight": row.weight,
                "exclusion_reason": row.exclusion_reason,
            }
            for row in sorted(rows, key=lambda item: (
                item.work_date, item.shift or 0, item.pool_id,
                item.project_id or "", item.order_no or "", item.part_no or "",
            ))
        ],
    }


async def create_external_load_snapshot(
        db: AsyncSession, *, captured_at: datetime, source: str,
        schema_version: str, coverage_start: date, coverage_end: date,
        tracked_programs: list[str], quality_policy: dict,
        assumption_ids: list[int], rows: list[dict]) -> ExternalLoadSnapshot:
    """Persist a complete immutable source copy; callers supply already classified rows."""
    if coverage_end < coverage_start:
        raise ValueError("External-load coverage_end must not precede coverage_start")
    policy = quality_policy.get("beyond_horizon")
    if policy not in BEYOND_HORIZON_POLICIES:
        raise ValueError("External-load beyond_horizon policy is required")
    snapshot = ExternalLoadSnapshot(
        captured_at=captured_at.replace(tzinfo=None), source=source,
        schema_version=schema_version, coverage_start=coverage_start,
        coverage_end=coverage_end,
        tracked_programs_json=_canonical_json(sorted(set(tracked_programs))),
        quality_policy_json=_canonical_json(quality_policy),
        assumption_ids_json=_canonical_json(sorted(set(assumption_ids))),
        content_hash="",
    )
    stored_rows = []
    for item in rows:
        normalized = dict(item)
        normalized["hours"] = float(normalized.get("hours", 0))
        normalized["weight"] = float(normalized.get("weight", 1))
        if normalized.get("units") is not None:
            normalized["units"] = float(normalized["units"])
        stored_rows.append(ExternalLoadRow(snapshot_id=0, **normalized))
    payload = _snapshot_payload(snapshot, stored_rows)
    snapshot.content_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    existing = await db.scalar(select(ExternalLoadSnapshot).where(
        ExternalLoadSnapshot.content_hash == snapshot.content_hash))
    if existing is not None:
        return existing
    db.add(snapshot)
    await db.flush()
    for row in stored_rows:
        row.snapshot_id = snapshot.id
        db.add(row)
    await db.flush()
    return snapshot


async def assess_external_snapshot(
        db: AsyncSession, snapshot_id: int, *, as_of: date,
        horizon_end: date) -> ExternalSnapshotAssessment:
    snapshot = await db.get(ExternalLoadSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError("External-load snapshot not found")
    rows = (await db.execute(select(ExternalLoadRow).where(
        ExternalLoadRow.snapshot_id == snapshot.id))).scalars().all()
    payload = _snapshot_payload(snapshot, rows)
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    if digest != snapshot.content_hash:
        raise RuntimeError("External-load snapshot content hash does not match stored rows")
    policy = payload["quality_policy"].get("beyond_horizon")
    if policy not in BEYOND_HORIZON_POLICIES:
        raise RuntimeError("External-load snapshot has no valid beyond-horizon policy")
    issues = []
    if snapshot.coverage_start > as_of:
        issues.append(CoverageIssue(
            "EXTERNAL_LOAD", "coverage_start", "MISSING",
            "External load starts after the simulation as-of date",
        ))
    if snapshot.coverage_end < horizon_end:
        if policy == "BLOCK":
            issues.append(CoverageIssue(
                "EXTERNAL_LOAD", "coverage_end", "MISSING",
                "External load does not cover the forecast horizon and policy is BLOCK",
            ))
        else:
            policy_id = payload["quality_policy"].get("policy_assumption_id")
            assumption = await db.get(ModelAssumption, policy_id) if policy_id else None
            open_review = (await db.scalar(select(AssumptionReview.id).where(
                AssumptionReview.assumption_id == policy_id,
                AssumptionReview.status == "OPEN",
            ))) if policy_id else None
            if (assumption is None or assumption.approval_status != "APPROVED"
                    or assumption.commitment_grade != "COMMITMENT_READY"):
                issues.append(CoverageIssue(
                    "EXTERNAL_LOAD", "beyond_horizon", "MISSING",
                    "External extrapolation policy has no approved commitment-ready assumption",
                ))
            elif (assumption.review_due_at is not None
                  and assumption.review_due_at < as_of) or open_review:
                issues.append(CoverageIssue(
                    "EXTERNAL_LOAD", "beyond_horizon", "PROVISIONAL",
                    "External extrapolation policy requires recertification",
                ))
    return ExternalSnapshotAssessment(
        snapshot_id=snapshot.id, payload=payload,
        assumption_ids=tuple(payload["assumption_ids"]), issues=tuple(issues),
    )
