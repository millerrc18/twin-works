"""Physical labor-pool allocation and shadow-comparison coverage."""
from datetime import date, datetime

import pytest

from capacity_engine import (
    InvalidPhysicalResourceProfile,
    MissingPhysicalResource,
    simulate,
)


def _profile(*, operation_pools, pool_budgets, reserves=None):
    factors = {str(day): 1.0 for day in range(7)}
    return {
        "resource_mode": "DB_SHADOW",
        "allocation_mode": "PHYSICAL",
        "crew_by_program": {},
        "dpas_programs": set(),
        "shift_budgets": {},
        "budget_programs": sorted({program for program, _opno in operation_pools}),
        "shared_wcs": set(),
        "operation_pools": operation_pools,
        "pool_shift_budgets": pool_budgets,
        "pool_external_reserves": reserves or {},
        "pool_calendar_policies": {
            pool: {
                "mode": "WEEKDAY_FACTORS", "factors": factors,
                "exceptions": {}, "covered_until": "2027-12-31",
            }
            for pool in pool_budgets
        },
        "pool_assumption_ids": {pool: () for pool in pool_budgets},
        "cure_station_capacities": {},
        "cure_station_rules": {},
        "parallel_cure_gates": {},
    }


def test_different_wc_labels_bound_to_one_pool_share_one_budget():
    ops = {
        "P1": [(100, "Program one work", "WC-A", 8.0, "SHIP")],
        "P2": [(100, "Program two work", "WC-B", 8.0, "SHIP")],
    }
    units = {
        "P1": [{"serial": "P1-1", "so": "1", "maxop": 0,
                "commit": date(2026, 8, 31), "program": "P1"}],
        "P2": [{"serial": "P2-1", "so": "2", "maxop": 0,
                "commit": date(2026, 8, 31), "program": "P2"}],
    }
    profile = _profile(
        operation_pools={("P1", 100): "SITE59:FINISH", ("P2", 100): "SITE59:FINISH"},
        pool_budgets={"SITE59:FINISH": {1: 8.0, 2: 0.0, 3: 0.0}},
    )

    from app.engines.rtg_wrapper import run_pooled
    result = run_pooled(
        units, datetime(2026, 8, 31, 6), ops_map=ops,
        cures_map={"P1": [], "P2": []}, profile=profile,
    )

    assert result["P1-1"]["finish"] == datetime(2026, 8, 31, 14)
    assert result["P2-1"]["finish"] == datetime(2026, 9, 1, 14)
    reversed_result = run_pooled(
        {"P2": units["P2"], "P1": units["P1"]},
        datetime(2026, 8, 31, 6), ops_map=ops,
        cures_map={"P1": [], "P2": []}, profile=profile,
    )
    assert reversed_result == result


def test_separate_physical_pools_do_not_merge_within_one_program():
    ops = {
        "P1": [
            (100, "First cell", "WC-A", 4.0, "BUILD"),
            (200, "Second cell", "WC-B", 4.0, "SHIP"),
        ],
    }
    profile = _profile(
        operation_pools={("P1", 100): "POOL-A", ("P1", 200): "POOL-B"},
        pool_budgets={
            "POOL-A": {1: 4.0, 2: 0.0, 3: 0.0},
            "POOL-B": {1: 4.0, 2: 0.0, 3: 0.0},
        },
    )

    result = simulate(
        [{"serial": "P1-1", "so": "1", "maxop": 0,
          "commit": date(2026, 8, 31), "program": "P1"}],
        ops, {"P1": []}, datetime(2026, 8, 31, 6), profile=profile,
    )

    assert result["P1-1"]["finish"] == datetime(2026, 8, 31, 14)


def test_static_external_reserve_reduces_gross_pool_capacity_and_is_explained():
    ops = {"P1": [(100, "Shared work", "WC-A", 8.0, "SHIP")]}
    profile = _profile(
        operation_pools={("P1", 100): "POOL-A"},
        pool_budgets={"POOL-A": {1: 8.0, 2: 0.0, 3: 0.0}},
        reserves={"POOL-A": {1: 4.0, 2: 0.0, 3: 0.0}},
    )

    result = simulate(
        [{"serial": "P1-1", "so": "1", "maxop": 0,
          "commit": date(2026, 8, 31), "program": "P1"}],
        ops, {"P1": []}, datetime(2026, 8, 31, 6), profile=profile,
        trace_constraints=True,
    )["P1-1"]

    assert result["finish"] == datetime(2026, 9, 1, 10)
    wait = next(event for event in result["constraint_events"]
                if event["pool_code"] == "POOL-A")
    assert wait["gross_capacity"] == 8.0
    assert wait["external_reserve"] == 4.0
    assert wait["schedulable_capacity"] == 4.0
    assert wait["requested_hours"] == 8.0
    assert wait["allocated_hours"] == 4.0


def test_physical_mode_never_uses_default_shift_for_an_unbound_operation():
    with pytest.raises(MissingPhysicalResource, match="P1 operation 100"):
        simulate(
            [{"serial": "P1-1", "so": "1", "maxop": 0,
              "commit": date(2026, 8, 31), "program": "P1"}],
            {"P1": [(100, "Unbound", "UNKNOWN", 1.0, "SHIP")]},
            {"P1": []}, datetime(2026, 8, 31, 6),
            profile=_profile(operation_pools={}, pool_budgets={}),
        )


def test_calendar_exceptions_and_coverage_end_are_enforced():
    unit = [{"serial": "P1-1", "so": "1", "maxop": 0,
             "commit": date(2026, 8, 31), "program": "P1"}]
    ops = {"P1": [(100, "Shared work", "WC-A", 8.0, "SHIP")]}
    profile = _profile(
        operation_pools={("P1", 100): "POOL-A"},
        pool_budgets={"POOL-A": {1: 8.0, 2: 0.0, 3: 0.0}},
    )
    profile["pool_calendar_policies"]["POOL-A"]["exceptions"] = {
        "2026-08-31": 0.0,
    }
    result = simulate(
        unit, ops, {"P1": []}, datetime(2026, 8, 31, 6), profile=profile)
    assert result["P1-1"]["finish"] == datetime(2026, 9, 1, 14)

    profile["pool_calendar_policies"]["POOL-A"]["covered_until"] = "2026-08-31"
    with pytest.raises(InvalidPhysicalResourceProfile, match="calendar ends"):
        simulate(
            unit, ops, {"P1": []}, datetime(2026, 8, 31, 6), profile=profile)


def test_shadow_comparison_names_pool_and_assumptions_for_a_changed_unit():
    from app.services.resource_shadow import compare_resource_profiles

    units = {
        "P1": [{"serial": "P1-1", "so": "1", "maxop": 0,
                "commit": date(2026, 8, 31), "program": "P1"}],
    }
    ops = {"P1": [(100, "Shared work", "WC-A", 8.0, "SHIP")]}
    baseline = _profile(
        operation_pools={("P1", 100): "POOL-A"},
        pool_budgets={"POOL-A": {1: 8.0, 2: 0.0, 3: 0.0}},
    )
    candidate = _profile(
        operation_pools={("P1", 100): "POOL-A"},
        pool_budgets={"POOL-A": {1: 8.0, 2: 0.0, 3: 0.0}},
        reserves={"POOL-A": {1: 4.0, 2: 0.0, 3: 0.0}},
    )
    candidate["pool_assumption_ids"] = {"POOL-A": (41, 42)}

    report = compare_resource_profiles(
        units, datetime(2026, 8, 31, 6), baseline, candidate,
        ops_map=ops, cures_map={"P1": []},
    )

    assert not report.exact_match
    assert report.changed_units == 1
    assert report.units[0].serial == "P1-1"
    assert report.units[0].delta_hours == 20.0
    assert report.units[0].causal_pools == ("POOL-A",)
    assert report.units[0].assumption_ids == (41, 42)


def test_frozen_replay_groups_programs_by_physical_pool_not_wc_label():
    from app.services.resource_profile import _frozen_pool_groups

    profile = {
        "scheduler_profile": {
            "allocation_mode": "PHYSICAL",
            "operation_pools": {"P1|100": "POOL-A", "P2|200": "POOL-A"},
        },
    }

    assert _frozen_pool_groups(["P2", "P1"], profile) == [["P1", "P2"]]
