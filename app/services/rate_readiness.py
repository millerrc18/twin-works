"""Pure RATE-01 demand, readiness, staffing, and measurement contracts."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING


READINESS_ORDER = {"READY": 0, "PROVISIONAL": 1, "UNRESOLVED": 2}


class RatePlanError(ValueError):
    """A rate-planning input cannot be canonicalized safely."""


@dataclass(frozen=True)
class DemandInput:
    program: str
    mode: str
    rate: Decimal
    start_month: date
    months: int
    product_mix: dict[str, Decimal]
    monthly_profile: tuple[Decimal, ...] | None = None


@dataclass(frozen=True)
class DemandMonth:
    program: str
    month: date
    units: int
    cumulative_units: int
    mix_units: dict[str, int]


@dataclass(frozen=True)
class CanonicalDemand:
    months: tuple[DemandMonth, ...]


@dataclass(frozen=True)
class WorkingCalendar:
    working_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    shutdown_dates: tuple[date, ...] = ()


@dataclass(frozen=True)
class SyntheticRelease:
    scenario_unit_id: str
    program: str
    variant: str
    release_date: date
    shop_order: None = None


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    resource_type: str
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class ReadinessAssessment:
    overall: str
    definitive: bool
    items: tuple[ReadinessItem, ...]


@dataclass(frozen=True)
class StaffingEvidence:
    skill_pool: str
    current_fte: Decimal
    productive_hours_per_fte: Decimal | None
    learning_curve: tuple[Decimal, ...] | None
    retention_yield: Decimal | None


@dataclass(frozen=True)
class StaffingGap:
    skill_pool: str
    required_hours: Decimal
    steady_state_required_fte: Decimal | None
    additional_fte: Decimal | None
    status: str


@dataclass(frozen=True)
class SustainabilityResult:
    measurement_demand: int
    measurement_completions: int
    measurement_backlog_start: int
    measurement_backlog_end: int
    cooldown_backlog_end: int
    backlog_slope_per_period: Decimal
    sustainable: bool


def _month_offset(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _cumulative_mix(total: int, mix: dict[str, Decimal]) -> dict[str, int]:
    ideals = {key: Decimal(total) * weight for key, weight in mix.items()}
    result = {key: _floor(value) for key, value in ideals.items()}
    remaining = total - sum(result.values())
    order = sorted(
        mix,
        key=lambda key: (-(ideals[key] - Decimal(result[key])), key),
    )
    for key in order[:remaining]:
        result[key] += 1
    return result


def canonicalize_demand(
        inputs: list[DemandInput], *, active_programs: set[str]) -> CanonicalDemand:
    """Convert rate inputs to deterministic integer monthly demand and product mix."""
    active = {program.upper() for program in active_programs}
    output = []
    for item in inputs:
        program = item.program.upper()
        if program not in active:
            raise RatePlanError(f"inactive program {program}")
        mode = item.mode.upper()
        if mode not in {"MONTHLY", "ANNUAL", "PROFILE"}:
            raise RatePlanError(f"invalid rate mode {item.mode}")
        rate = Decimal(item.rate)
        if rate < 0:
            raise RatePlanError("rate cannot be negative")
        if item.months <= 0:
            raise RatePlanError("months must be positive")
        if item.start_month.day != 1:
            raise RatePlanError("start_month must be the first day of a month")
        mix = {str(key).strip(): Decimal(value)
               for key, value in item.product_mix.items() if str(key).strip()}
        if not mix or any(value <= 0 for value in mix.values()) or sum(mix.values()) != 1:
            raise RatePlanError("product mix must sum to 1")
        if mode == "PROFILE":
            profile = tuple(Decimal(value) for value in (item.monthly_profile or ()))
            if len(profile) != item.months or any(value < 0 for value in profile):
                raise RatePlanError(
                    "monthly profile must contain one non-negative value per month")
        else:
            monthly_rate = rate / Decimal(12) if mode == "ANNUAL" else rate
            profile = tuple(monthly_rate for _ in range(item.months))
        prior_total = 0
        prior_mix = {key: 0 for key in mix}
        cumulative_target = Decimal(0)
        for offset in range(item.months):
            cumulative_target += profile[offset]
            cumulative = _floor(cumulative_target)
            units = cumulative - prior_total
            cumulative_mix = _cumulative_mix(cumulative, mix)
            month_mix = {
                key: cumulative_mix[key] - prior_mix[key]
                for key in sorted(mix)
            }
            output.append(DemandMonth(
                program=program,
                month=_month_offset(item.start_month, offset),
                units=units,
                cumulative_units=cumulative,
                mix_units=month_mix,
            ))
            prior_total = cumulative
            prior_mix = cumulative_mix
    output.sort(key=lambda row: (row.month, row.program))
    return CanonicalDemand(months=tuple(output))


def _working_days(month: date, policy: WorkingCalendar) -> list[date]:
    shutdowns = set(policy.shutdown_dates)
    allowed = set(policy.working_weekdays)
    if not allowed or any(day < 0 or day > 6 for day in allowed):
        raise RatePlanError("working weekdays must be between 0 and 6")
    return [
        date(month.year, month.month, day)
        for day in range(1, calendar.monthrange(month.year, month.month)[1] + 1)
        if date(month.year, month.month, day).weekday() in allowed
        and date(month.year, month.month, day) not in shutdowns
    ]


def build_release_calendar(
        scenario_key: str, demand: CanonicalDemand,
        working_calendar: WorkingCalendar) -> tuple[SyntheticRelease, ...]:
    """Spread scenario-only releases deterministically across eligible working days."""
    releases = []
    sequence_by_program: dict[str, int] = {}
    for month in demand.months:
        days = _working_days(month.month, working_calendar)
        if month.units and not days:
            raise RatePlanError(f"no working days in {month.month.isoformat()}")
        variants = [
            variant
            for variant in sorted(month.mix_units)
            for _ in range(month.mix_units[variant])
        ]
        for index, variant in enumerate(variants):
            day = days[(index * len(days)) // len(variants)]
            sequence = sequence_by_program.get(month.program, 0) + 1
            sequence_by_program[month.program] = sequence
            releases.append(SyntheticRelease(
                scenario_unit_id=(
                    f"RATE:{scenario_key}:{month.program}:{sequence:05d}"),
                program=month.program,
                variant=variant,
                release_date=day,
            ))
    return tuple(releases)


def releases_as_sim_units(
        releases: tuple[SyntheticRelease, ...], *, shift_start_hour: int = 6) -> list[dict]:
    """Convert synthetic releases to scheduler inputs without operational identities."""
    return [
        {
            "serial": release.scenario_unit_id,
            "so": release.scenario_unit_id,
            "maxop": 0,
            "commit": release.release_date,
            "program": release.program,
            "variant": release.variant,
            "release_at": datetime.combine(
                release.release_date, time(hour=shift_start_hour)),
            "scenario_only": True,
        }
        for release in releases
    ]


def assess_readiness(items: list[ReadinessItem]) -> ReadinessAssessment:
    normalized = []
    for item in items:
        status = item.status.upper()
        if status not in READINESS_ORDER:
            raise RatePlanError(f"invalid readiness status {item.status}")
        normalized.append(ReadinessItem(
            key=item.key,
            resource_type=item.resource_type.upper(),
            status=status,
            reason=item.reason,
        ))
    overall = max(
        (item.status for item in normalized),
        key=lambda status: READINESS_ORDER[status],
        default="READY",
    )
    return ReadinessAssessment(
        overall=overall,
        definitive=(overall == "READY"),
        items=tuple(normalized),
    )


def tool_addition(
        readiness: ReadinessAssessment, resource_key: str,
        current_slots: int, required_slots: int) -> int | None:
    item = next((row for row in readiness.items if row.key == resource_key), None)
    if item is None or item.status == "UNRESOLVED":
        return None
    return max(0, required_slots - current_slots)


def staffing_gap(required_hours: Decimal, evidence: StaffingEvidence) -> StaffingGap:
    hours = Decimal(required_hours)
    productive = evidence.productive_hours_per_fte
    if productive is None or productive <= 0:
        return StaffingGap(
            skill_pool=evidence.skill_pool,
            required_hours=hours,
            steady_state_required_fte=None,
            additional_fte=None,
            status="UNRESOLVED",
        )
    required = (hours / productive).to_integral_value(rounding=ROUND_CEILING)
    additional = max(Decimal(0), required - evidence.current_fte)
    status = ("READY" if evidence.learning_curve is not None
              and evidence.retention_yield is not None else "PROVISIONAL")
    return StaffingGap(
        skill_pool=evidence.skill_pool,
        required_hours=hours,
        steady_state_required_fte=required,
        additional_fte=additional,
        status=status,
    )


def measure_sustainability(
        *, releases: tuple[int, ...], completions: tuple[int, ...],
        warmup_periods: int, measurement_periods: int, cooldown_periods: int,
        backlog_tolerance: int, initial_backlog: int = 0) -> SustainabilityResult:
    expected = warmup_periods + measurement_periods + cooldown_periods
    if len(releases) != expected or len(completions) != expected:
        raise RatePlanError("period vectors do not match the configured horizon")
    if measurement_periods <= 0 or min(
            warmup_periods, cooldown_periods, backlog_tolerance, initial_backlog) < 0:
        raise RatePlanError("measurement and backlog settings are invalid")
    if any(value < 0 for value in releases + completions):
        raise RatePlanError("release and completion counts cannot be negative")

    backlog = initial_backlog
    measurement_start = None
    measurement_end = None
    measurement_demand = 0
    measurement_completions = 0
    measurement_stop = warmup_periods + measurement_periods
    for index, (released, completed) in enumerate(zip(releases, completions)):
        if index == warmup_periods:
            measurement_start = backlog
        available = backlog + released
        if completed > available:
            raise RatePlanError("completions cannot exceed available work")
        backlog = available - completed
        if warmup_periods <= index < measurement_stop:
            measurement_demand += released
            measurement_completions += completed
        if index == measurement_stop - 1:
            measurement_end = backlog

    assert measurement_start is not None and measurement_end is not None
    change = measurement_end - measurement_start
    slope = Decimal(change) / Decimal(measurement_periods)
    return SustainabilityResult(
        measurement_demand=measurement_demand,
        measurement_completions=measurement_completions,
        measurement_backlog_start=measurement_start,
        measurement_backlog_end=measurement_end,
        cooldown_backlog_end=backlog,
        backlog_slope_per_period=slope,
        sustainable=(measurement_completions >= measurement_demand
                     and change <= backlog_tolerance),
    )
