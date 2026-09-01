"""Validated, non-active modeling policy for the quarantined BCA layup stream."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


POLICY_PATH = Path(__file__).with_name("bca_layup_policy.v1.json")


class LayupPolicyError(ValueError):
    pass


@lru_cache(maxsize=1)
def load_bca_layup_policy() -> dict:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("schema_version") != 1 or policy.get("stream_key") != "BCALAY":
        raise LayupPolicyError("Invalid BCA layup policy identity")
    if policy.get("onboarding_status") != "BLOCKED":
        raise LayupPolicyError("BCA layup must remain blocked until every policy gate closes")
    resources = {item["resource_key"]: item for item in policy.get("resources", [])}
    expected = {"59:TRI_L_LABOR", "59:ATUP_OPERATOR", "59:ATUP_AUTOCLAVE"}
    if set(resources) != expected:
        raise LayupPolicyError("BCA layup resource boundary is incomplete")
    tri_l = resources["59:TRI_L_LABOR"]
    if (tri_l.get("requirement_mode") != "EFFORT"
            or tri_l.get("machine_time_semantics") != "EVIDENCE_ONLY_NOT_ADDITIVE"
            or tri_l.get("capacity_status") != "UNAPPROVED"):
        raise LayupPolicyError("TRI L effort semantics are not conservative")
    autoclave = resources["59:ATUP_AUTOCLAVE"]
    if (autoclave.get("requirement_mode") != "OCCUPANCY"
            or autoclave.get("minimum_hold_hours") != 6.0
            or autoclave.get("slot_count") is not None
            or autoclave.get("capacity_status") != "UNAPPROVED"):
        raise LayupPolicyError("ATUP occupancy semantics are not safely blocked")
    return policy
