"""Deterministic, explainable comparisons between resource profiles."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

from app.engines.rtg_wrapper import run_pooled


@dataclass(frozen=True)
class UnitResourceDiff:
    serial: str
    program: str
    baseline_finish: datetime
    candidate_finish: datetime
    delta_hours: float
    causal_pools: tuple[str, ...]
    assumption_ids: tuple[int, ...]
    waits: tuple[dict, ...]


@dataclass(frozen=True)
class ResourceShadowReport:
    exact_match: bool
    changed_units: int
    units: tuple[UnitResourceDiff, ...]


def compare_resource_profiles(units_by_program: dict, as_of: datetime,
                              baseline_profile: dict, candidate_profile: dict,
                              *, ops_map=None, cures_map=None) -> ResourceShadowReport:
    """Compare profiles over identical WIP and retain the candidate's causal waits."""
    baseline = run_pooled(
        deepcopy(units_by_program), as_of, profile=baseline_profile,
        ops_map=ops_map, cures_map=cures_map,
    )
    candidate = run_pooled(
        deepcopy(units_by_program), as_of, profile=candidate_profile,
        ops_map=ops_map, cures_map=cures_map, trace_constraints=True,
    )
    program_by_serial = {
        unit["serial"]: program
        for program, units in units_by_program.items()
        for unit in units
    }
    pool_assumptions = candidate_profile.get("pool_assumption_ids", {})
    changes = []
    for serial in sorted(set(baseline) | set(candidate)):
        before = baseline.get(serial)
        after = candidate.get(serial)
        if before is None or after is None:
            continue
        if (before["finish"] == after["finish"]
                and before.get("op_dt") == after.get("op_dt")
                and before.get("cure_dt") == after.get("cure_dt")):
            continue
        waits = tuple(after.get("constraint_events", ()))
        pools = tuple(sorted({event["pool_code"] for event in waits}))
        assumption_ids = tuple(sorted({
            int(assumption_id)
            for pool in pools
            for assumption_id in pool_assumptions.get(pool, ())
        }))
        changes.append(UnitResourceDiff(
            serial=serial,
            program=program_by_serial.get(serial, ""),
            baseline_finish=before["finish"],
            candidate_finish=after["finish"],
            delta_hours=round(
                (after["finish"] - before["finish"]).total_seconds() / 3600.0, 3),
            causal_pools=pools,
            assumption_ids=assumption_ids,
            waits=waits,
        ))
    return ResourceShadowReport(
        exact_match=not changes, changed_units=len(changes), units=tuple(changes),
    )
