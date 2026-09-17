"""RATE-01a/b demand, readiness, and steady-state contracts."""
from datetime import date
from decimal import Decimal

import pytest


def test_annual_rate_accumulates_fractional_months_without_losing_units():
    from app.services.rate_readiness import DemandInput, canonicalize_demand

    demand = canonicalize_demand(
        [DemandInput(
            program="RAD",
            mode="ANNUAL",
            rate=Decimal("17"),
            start_month=date(2026, 10, 1),
            months=12,
            product_mix={"RADOME": Decimal("1")},
        )],
        active_programs={"ELEV", "RAD", "AEGIS"},
    )

    assert sum(month.units for month in demand.months) == 17
    assert [month.units for month in demand.months[:4]] == [1, 1, 2, 1]
    assert demand.months[-1].cumulative_units == 17


def test_inactive_program_and_invalid_mix_fail_closed():
    from app.services.rate_readiness import DemandInput, RatePlanError, canonicalize_demand

    with pytest.raises(RatePlanError, match="inactive program BCAFIN"):
        canonicalize_demand([
            DemandInput(
                program="BCAFIN", mode="MONTHLY", rate=Decimal("1"),
                start_month=date(2026, 10, 1), months=3,
                product_mix={"A": Decimal("1")},
            )
        ], active_programs={"ELEV", "RAD", "AEGIS"})

    with pytest.raises(RatePlanError, match="product mix must sum to 1"):
        canonicalize_demand([
            DemandInput(
                program="RAD", mode="MONTHLY", rate=Decimal("1"),
                start_month=date(2026, 10, 1), months=3,
                product_mix={"A": Decimal("0.7"), "B": Decimal("0.2")},
            )
        ], active_programs={"RAD"})


def test_product_mix_allocation_is_deterministic_and_balanced():
    from app.services.rate_readiness import DemandInput, canonicalize_demand

    demand = canonicalize_demand([
        DemandInput(
            program="ELEV", mode="MONTHLY", rate=Decimal("3"),
            start_month=date(2026, 10, 1), months=2,
            product_mix={"LH": Decimal("0.5"), "RH": Decimal("0.5")},
        )
    ], active_programs={"ELEV"})

    assert [month.mix_units for month in demand.months] == [
        {"LH": 2, "RH": 1},
        {"LH": 1, "RH": 2},
    ]


def test_explicit_monthly_profile_is_preserved_exactly():
    from app.services.rate_readiness import DemandInput, canonicalize_demand

    demand = canonicalize_demand([
        DemandInput(
            program="RAD", mode="PROFILE", rate=Decimal("0"),
            start_month=date(2026, 10, 1), months=3,
            product_mix={"RADOME": Decimal("1")},
            monthly_profile=(Decimal("1"), Decimal("2"), Decimal("4")),
        )
    ], active_programs={"RAD"})

    assert [month.units for month in demand.months] == [1, 2, 4]
    assert demand.months[-1].cumulative_units == 7


def test_release_calendar_uses_workdays_and_never_creates_operational_ids():
    from app.services.rate_readiness import (
        DemandInput,
        WorkingCalendar,
        build_release_calendar,
        canonicalize_demand,
    )

    demand = canonicalize_demand([
        DemandInput(
            program="RAD", mode="MONTHLY", rate=Decimal("3"),
            start_month=date(2026, 11, 1), months=1,
            product_mix={"RADOME": Decimal("1")},
        )
    ], active_programs={"RAD"})
    releases = build_release_calendar(
        "RATE-TEST", demand,
        WorkingCalendar(working_weekdays=(0, 1, 2, 3, 4),
                        shutdown_dates=(date(2026, 11, 11),)),
    )

    assert len(releases) == 3
    assert all(release.release_date.weekday() < 5 for release in releases)
    assert all(release.release_date != date(2026, 11, 11) for release in releases)
    assert all(release.scenario_unit_id.startswith("RATE:RATE-TEST:RAD:")
               for release in releases)
    assert all(release.shop_order is None for release in releases)


def test_future_synthetic_release_cannot_start_before_release_date():
    from datetime import datetime

    from capacity_engine import simulate
    from app.services.rate_readiness import SyntheticRelease, releases_as_sim_units

    release = SyntheticRelease(
        scenario_unit_id="RATE:TEST:RAD:00001",
        program="RAD",
        variant="RADOME",
        release_date=date(2026, 10, 12),
    )
    units = releases_as_sim_units((release,))
    result = simulate(
        units,
        {"RAD": [(100, "Work", "AEROA", 1.0, "FLOW")]},
        {"RAD": []},
        datetime(2026, 10, 1, 6),
        profile={
            "shift_budgets": {("RAD", "AEROA"): {1: 8, 2: 0, 3: 0}},
            "budget_programs": ["RAD"],
            "dpas_programs": set(),
            "cure_station_capacities": {},
            "cure_station_rules": {},
        },
    )

    assert result[release.scenario_unit_id]["op_dt"][100] >= datetime(2026, 10, 12, 6)


def test_unresolved_tooling_blocks_definitive_feasibility_and_never_returns_zero():
    from app.services.rate_readiness import (
        ReadinessItem,
        assess_readiness,
        tool_addition,
    )

    assessment = assess_readiness([
        ReadinessItem("RAD:AEROA", "LABOR", "READY"),
        ReadinessItem(
            "AERONOSE_HOLDING_FIXTURE", "TOOL", "UNRESOLVED",
            "Acquire/release span missing"),
    ])

    assert assessment.overall == "UNRESOLVED"
    assert not assessment.definitive
    assert tool_addition(assessment, "AERONOSE_HOLDING_FIXTURE", 1, 2) is None


def test_missing_productive_hours_yields_hours_gap_not_headcount():
    from app.services.rate_readiness import StaffingEvidence, staffing_gap

    gap = staffing_gap(
        required_hours=Decimal("320"),
        evidence=StaffingEvidence(
            skill_pool="RAD_ASSEMBLY",
            current_fte=Decimal("4"),
            productive_hours_per_fte=None,
            learning_curve=None,
            retention_yield=None,
        ),
    )

    assert gap.required_hours == Decimal("320")
    assert gap.additional_fte is None
    assert gap.status == "UNRESOLVED"


def test_cooldown_cannot_hide_measurement_backlog_growth():
    from app.services.rate_readiness import measure_sustainability

    result = measure_sustainability(
        releases=(2, 2, 0),
        completions=(1, 1, 2),
        warmup_periods=0,
        measurement_periods=2,
        cooldown_periods=1,
        backlog_tolerance=0,
    )

    assert result.measurement_backlog_start == 0
    assert result.measurement_backlog_end == 2
    assert result.cooldown_backlog_end == 0
    assert result.backlog_slope_per_period == Decimal("1")
    assert not result.sustainable
