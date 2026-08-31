"""Versioned evidence payloads for governed model assumptions."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any


SUPPORTED_EVIDENCE_SCHEMAS = {1}


class EvidenceValidationError(ValueError):
    pass


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"Evidence {field} must be non-empty text")
    return value.strip()


def _iso_value(value: Any, field: str, *, require_timezone: bool = False) -> str:
    value = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        if require_timezone:
            raise EvidenceValidationError(
                f"Evidence {field} must be an ISO datetime with timezone") from exc
        try:
            date.fromisoformat(value)
        except ValueError:
            raise EvidenceValidationError(
                f"Evidence {field} must be an ISO date or datetime") from exc
    else:
        if require_timezone and parsed.tzinfo is None:
            raise EvidenceValidationError(f"Evidence {field} must include a timezone")
    return value


def canonical_evidence(payload: dict, *, schema_version: int,
                       require_complete: bool) -> str:
    """Validate and serialize one immutable evidence object."""
    if schema_version not in SUPPORTED_EVIDENCE_SCHEMAS:
        raise EvidenceValidationError(
            f"Unsupported evidence schema version: {schema_version}")
    if not isinstance(payload, dict):
        raise EvidenceValidationError("Evidence payload must be a JSON object")
    if not payload and not require_complete:
        return "{}"
    if payload.get("schema_version") != schema_version:
        raise EvidenceValidationError(
            "Evidence schema_version must match evidence_schema_version")
    source_refs = payload.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        raise EvidenceValidationError("Evidence source_refs must be a non-empty list")
    for index, source in enumerate(source_refs):
        _required_text(source, f"source_refs[{index}]")
    _required_text(payload.get("captured_by"), "captured_by")
    _iso_value(payload.get("captured_at"), "captured_at", require_timezone=True)
    _required_text(payload.get("method"), "method")

    window = payload.get("window")
    if window is not None:
        if not isinstance(window, dict):
            raise EvidenceValidationError("Evidence window must be an object")
        start = _iso_value(window.get("start"), "window.start")
        end = _iso_value(window.get("end"), "window.end")
        if date.fromisoformat(start[:10]) > date.fromisoformat(end[:10]):
            raise EvidenceValidationError("Evidence window start must not exceed end")
    sample_count = payload.get("sample_count")
    if sample_count is not None and (
            isinstance(sample_count, bool) or not isinstance(sample_count, int)
            or sample_count < 0):
        raise EvidenceValidationError("Evidence sample_count must be a non-negative integer")
    drift_policy = payload.get("drift_policy")
    if drift_policy is not None:
        if not isinstance(drift_policy, dict):
            raise EvidenceValidationError("Evidence drift_policy must be an object")
        threshold = drift_policy.get("relative_threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold <= 0:
            raise EvidenceValidationError(
                "Evidence drift_policy.relative_threshold must be positive")
        minimum = drift_policy.get("minimum_samples", 1)
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
            raise EvidenceValidationError(
                "Evidence drift_policy.minimum_samples must be a positive integer")
    try:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceValidationError("Evidence must contain deterministic JSON values") from exc


def build_evidence(*, schema_version: int, subject_type: str, subject_key: str,
                   parameter: str, basis: str, evidence_source: str | None,
                   evidence_start: date | None, evidence_end: date | None,
                   calculation_method: str | None, evidence_count: int | None,
                   owner: str | None, approver: str | None,
                   effective_from: date, captured_at: datetime | None = None) -> dict:
    """Build a complete v1 payload from the typed legacy provenance columns."""
    captured_at = captured_at or datetime.now(timezone.utc)
    source = evidence_source or f"owner-confirmed:{subject_type}:{subject_key}:{parameter}"
    payload = {
        "schema_version": schema_version,
        "source_refs": [source],
        "captured_by": approver or owner or "TwinWorks",
        "captured_at": captured_at.isoformat(),
        "method": calculation_method or basis,
    }
    if evidence_start or evidence_end or basis == "MEASURED_ACTUAL":
        payload["window"] = {
            "start": (evidence_start or effective_from).isoformat(),
            "end": (evidence_end or evidence_start or effective_from).isoformat(),
        }
    if evidence_count is not None:
        payload["sample_count"] = evidence_count
    return payload
