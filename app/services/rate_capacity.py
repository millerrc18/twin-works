"""RATE-01b analytical capacity bounds and bounded sustainable-rate search."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from app.services.rate_readiness import SustainabilityResult


class RateCapacityError(ValueError):
    """Capacity inputs or search bounds are unsafe or incomplete."""


@dataclass(frozen=True)
class LaborLowerBound:
    pool_code: str
    internal_hours: Decimal
    external_hours: Decimal
    total_hours: Decimal
    average_hours_per_month: Decimal
    unit_count: int


@dataclass(frozen=True)
class LeaseInterval:
    pool_code: str
    start: datetime
    end: datetime
    quantity: int = 1


@dataclass(frozen=True)
class ToolLowerBound:
    pool_code: str
    required_slots: int
    peak_at: datetime


@dataclass(frozen=True)
class RateEvaluation:
    rate: Decimal
    result: SustainabilityResult


@dataclass(frozen=True)
class SustainableRateSearch:
    status: str
    highest_sustainable_rate: Decimal | None
    evaluations: tuple[RateEvaluation, ...]
    evaluated_count: int
    remaining_rate_count: int


def _decimal(value, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RateCapacityError(f"{field} must be numeric") from None
    if not result.is_finite():
        raise RateCapacityError(f"{field} must be finite")
    return result


def calculate_labor_lower_bounds(
        *, units_by_program: dict[str, list[dict]], ops_map: dict[str, list],
        operation_pools: dict[tuple[str, int], str], measurement_months: int,
        external_hours_by_pool_month: dict[tuple[str, date], Decimal] | None = None,
        ) -> dict[str, LaborLowerBound]:
    """Sum remaining route hours by physical pool, including governed external load."""
    if measurement_months <= 0:
        raise RateCapacityError("measurement_months must be positive")
    internal: dict[str, Decimal] = {}
    units_by_pool: dict[str, set[tuple[str, str]]] = {}
    for program, units in sorted(units_by_program.items()):
        if program not in ops_map:
            raise RateCapacityError(f"no routing for program {program}")
        for unit in units:
            maxop = unit.get("maxop")
            for opno, _description, _wc, hours, _milestone in ops_map[program]:
                if maxop is not None and int(opno) <= int(maxop):
                    continue
                pool = operation_pools.get((program, int(opno)))
                if not pool:
                    raise RateCapacityError(
                        f"{program} operation {opno} has no physical pool mapping")
                value = _decimal(hours, "operation hours")
                if value < 0:
                    raise RateCapacityError("operation hours cannot be negative")
                internal[pool] = internal.get(pool, Decimal(0)) + value
                units_by_pool.setdefault(pool, set()).add(
                    (program, str(unit.get("serial") or unit.get("so") or "")))

    external: dict[str, Decimal] = {}
    for (pool, month), value in sorted((external_hours_by_pool_month or {}).items()):
        if month.day != 1:
            raise RateCapacityError("external demand month must be the first day of a month")
        hours = _decimal(value, "external hours")
        if hours < 0:
            raise RateCapacityError("external hours cannot be negative")
        external[pool] = external.get(pool, Decimal(0)) + hours

    results = {}
    for pool in sorted(set(internal) | set(external)):
        internal_hours = internal.get(pool, Decimal(0))
        external_hours = external.get(pool, Decimal(0))
        total = internal_hours + external_hours
        results[pool] = LaborLowerBound(
            pool_code=pool,
            internal_hours=internal_hours,
            external_hours=external_hours,
            total_hours=total,
            average_hours_per_month=total / Decimal(measurement_months),
            unit_count=len(units_by_pool.get(pool, set())),
        )
    return results


def calculate_tool_lower_bounds(
        intervals: tuple[LeaseInterval, ...]) -> dict[str, ToolLowerBound]:
    """Return peak concurrent pooled slot demand from half-open lease intervals."""
    events: dict[str, list[tuple[datetime, int]]] = {}
    for row in intervals:
        if not row.pool_code.strip():
            raise RateCapacityError("lease pool_code is required")
        if row.end <= row.start:
            raise RateCapacityError("lease interval must end after start")
        if row.quantity <= 0:
            raise RateCapacityError("lease quantity must be positive")
        events.setdefault(row.pool_code, []).extend((
            (row.start, row.quantity),
            (row.end, -row.quantity),
        ))

    output = {}
    for pool, rows in sorted(events.items()):
        active = peak = 0
        peak_at = None
        # End events sort before start events, making intervals [start, end).
        for at, delta in sorted(rows, key=lambda item: (item[0], item[1])):
            active += delta
            if active < 0:
                raise RateCapacityError("lease events produced negative occupancy")
            if active > peak:
                peak = active
                peak_at = at
        if peak_at is None:
            raise RateCapacityError("tool lower bound has no positive occupancy")
        output[pool] = ToolLowerBound(
            pool_code=pool, required_slots=peak, peak_at=peak_at)
    return output


def _rate_grid(minimum: Decimal, maximum: Decimal, step: Decimal) -> tuple[Decimal, ...]:
    if step <= 0 or minimum < 0 or maximum < minimum:
        raise RateCapacityError("invalid sustainable-rate search bounds")
    rows = []
    value = minimum
    while value <= maximum:
        rows.append(value)
        value += step
    return tuple(rows)


def search_sustainable_rate(
        *, minimum: Decimal, maximum: Decimal, step: Decimal,
        evaluator: Callable[[Decimal], SustainabilityResult],
        max_evaluations: int) -> SustainableRateSearch:
    """Evaluate a bounded discrete rate grid without assuming monotonic feasibility."""
    if max_evaluations <= 0:
        raise RateCapacityError("max_evaluations must be positive")
    grid = _rate_grid(
        _decimal(minimum, "minimum"),
        _decimal(maximum, "maximum"),
        _decimal(step, "step"),
    )
    selected = grid[:max_evaluations]
    evaluations = tuple(RateEvaluation(rate, evaluator(rate)) for rate in selected)
    sustainable = [row.rate for row in evaluations if row.result.sustainable]
    remaining = len(grid) - len(selected)
    return SustainableRateSearch(
        status="SEARCH_INCOMPLETE" if remaining else "COMPLETE",
        highest_sustainable_rate=max(sustainable) if sustainable else None,
        evaluations=evaluations,
        evaluated_count=len(evaluations),
        remaining_rate_count=remaining,
    )
