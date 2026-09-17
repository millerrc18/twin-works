"""RATE-01b analytical lower bounds and bounded rate search."""
from datetime import date, datetime
from decimal import Decimal


def test_labor_lower_bounds_include_remaining_wip_synthetic_and_external_hours():
    from app.services.rate_capacity import calculate_labor_lower_bounds

    units = {
        "RAD": [
            {"serial": "WIP", "program": "RAD", "maxop": 100},
            {"serial": "RATE:1", "program": "RAD", "maxop": 0,
             "scenario_only": True},
        ],
    }
    bounds = calculate_labor_lower_bounds(
        units_by_program=units,
        ops_map={"RAD": [
            (100, "First", "AEROA", 10.0, "ASSY"),
            (200, "Second", "P3 QA", 4.0, "ASSY"),
        ]},
        operation_pools={
            ("RAD", 100): "RAD_SKILL",
            ("RAD", 200): "RAD_SKILL",
        },
        measurement_months=2,
        external_hours_by_pool_month={
            ("RAD_SKILL", date(2026, 10, 1)): Decimal("6"),
            ("RAD_SKILL", date(2026, 11, 1)): Decimal("4"),
        },
    )

    row = bounds["RAD_SKILL"]
    assert row.internal_hours == Decimal("18")
    assert row.external_hours == Decimal("10")
    assert row.total_hours == Decimal("28")
    assert row.average_hours_per_month == Decimal("14")
    assert row.unit_count == 2


def test_labor_lower_bounds_require_physical_pool_mapping():
    from app.services.rate_capacity import RateCapacityError, calculate_labor_lower_bounds

    try:
        calculate_labor_lower_bounds(
            units_by_program={"RAD": [
                {"serial": "R1", "program": "RAD", "maxop": 0}]},
            ops_map={"RAD": [(100, "Work", "AEROA", 1.0, "ASSY")]},
            operation_pools={},
            measurement_months=1,
        )
    except RateCapacityError as exc:
        assert "no physical pool" in str(exc)
    else:
        raise AssertionError("missing physical pool mapping was accepted")


def test_labor_lower_bounds_are_independent_of_unit_and_route_input_order():
    from app.services.rate_capacity import calculate_labor_lower_bounds

    units = [
        {"serial": "A", "program": "RAD", "maxop": 0},
        {"serial": "B", "program": "RAD", "maxop": 100},
    ]
    ops = [
        (100, "First", "AEROA", 3.0, "ASSY"),
        (200, "Second", "AEROA", 2.0, "ASSY"),
    ]
    kwargs = dict(
        operation_pools={("RAD", 100): "RAD_SKILL", ("RAD", 200): "RAD_SKILL"},
        measurement_months=1,
    )
    first = calculate_labor_lower_bounds(
        units_by_program={"RAD": units}, ops_map={"RAD": ops}, **kwargs)
    second = calculate_labor_lower_bounds(
        units_by_program={"RAD": list(reversed(units))},
        ops_map={"RAD": list(reversed(ops))}, **kwargs)

    assert first == second


def test_tool_lower_bound_counts_overlap_and_reuses_at_touching_boundaries():
    from app.services.rate_capacity import LeaseInterval, calculate_tool_lower_bounds

    bounds = calculate_tool_lower_bounds((
        LeaseInterval("SHELL_MOLD", datetime(2026, 10, 1, 6),
                      datetime(2026, 10, 1, 12), 1),
        LeaseInterval("SHELL_MOLD", datetime(2026, 10, 1, 8),
                      datetime(2026, 10, 1, 10), 2),
        LeaseInterval("SHELL_MOLD", datetime(2026, 10, 1, 12),
                      datetime(2026, 10, 1, 16), 1),
    ))

    assert bounds["SHELL_MOLD"].required_slots == 3
    assert bounds["SHELL_MOLD"].peak_at == datetime(2026, 10, 1, 8)


def test_tool_lower_bound_rejects_invalid_interval():
    from app.services.rate_capacity import (
        LeaseInterval, RateCapacityError, calculate_tool_lower_bounds,
    )

    try:
        calculate_tool_lower_bounds((LeaseInterval(
            "BAD", datetime(2026, 10, 1, 8), datetime(2026, 10, 1, 8), 1),))
    except RateCapacityError as exc:
        assert "end after start" in str(exc)
    else:
        raise AssertionError("invalid lease interval was accepted")


def test_rate_search_evaluates_all_bounded_rates_and_handles_nonmonotonic_result():
    from app.services.rate_capacity import search_sustainable_rate
    from app.services.rate_readiness import SustainabilityResult

    sustainable = {Decimal("1"), Decimal("3")}

    def evaluate(rate):
        ok = rate in sustainable
        return SustainabilityResult(
            measurement_demand=int(rate),
            measurement_completions=int(rate) if ok else 0,
            measurement_backlog_start=0,
            measurement_backlog_end=0 if ok else int(rate),
            cooldown_backlog_end=0,
            backlog_slope_per_period=Decimal(0 if ok else 1),
            sustainable=ok,
        )

    result = search_sustainable_rate(
        minimum=Decimal("1"), maximum=Decimal("3"), step=Decimal("1"),
        evaluator=evaluate, max_evaluations=10)

    assert result.status == "COMPLETE"
    assert result.highest_sustainable_rate == Decimal("3")
    assert [row.rate for row in result.evaluations] == [
        Decimal("1"), Decimal("2"), Decimal("3")]


def test_rate_search_reports_search_incomplete_when_bound_is_exhausted():
    from app.services.rate_capacity import search_sustainable_rate
    from app.services.rate_readiness import SustainabilityResult

    def evaluate(rate):
        return SustainabilityResult(
            measurement_demand=int(rate), measurement_completions=int(rate),
            measurement_backlog_start=0, measurement_backlog_end=0,
            cooldown_backlog_end=0, backlog_slope_per_period=Decimal("0"),
            sustainable=True)

    result = search_sustainable_rate(
        minimum=Decimal("1"), maximum=Decimal("5"), step=Decimal("1"),
        evaluator=evaluate, max_evaluations=3)

    assert result.status == "SEARCH_INCOMPLETE"
    assert result.highest_sustainable_rate == Decimal("3")
    assert result.evaluated_count == 3
    assert result.remaining_rate_count == 2
