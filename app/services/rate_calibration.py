"""RATE-01c historical throughput, WIP, cycle-time, and labor calibration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class CalibrationError(ValueError):
    """Calibration evidence or thresholds are invalid."""


@dataclass(frozen=True)
class CalibrationOrder:
    order_no: str
    program: str
    actual_start: datetime
    actual_completion: datetime
    modeled_completion: datetime
    planned_labor_hours: Decimal
    actual_labor_hours: Decimal
    routing_revision: str


@dataclass(frozen=True)
class CalibrationFlowUnit:
    order_no: str
    program: str
    actual_start: datetime
    actual_completion: datetime | None
    modeled_completion: datetime


@dataclass(frozen=True)
class CalibrationPeriod:
    month: date
    actual_releases: int
    actual_completions: int
    modeled_completions: int
    actual_average_wip: Decimal
    modeled_average_wip: Decimal


@dataclass(frozen=True)
class CalibrationThresholds:
    minimum_orders: int
    cycle_mae_days_max: Decimal
    completion_wape_max: Decimal
    wip_wape_max: Decimal
    labor_wape_max: Decimal


@dataclass(frozen=True)
class CalibrationMetrics:
    sample_orders: int
    cycle_mae_days: Decimal | None
    cycle_bias_days: Decimal | None
    completion_wape: Decimal | None
    wip_wape: Decimal | None
    labor_wape: Decimal | None


@dataclass(frozen=True)
class ProgramCalibrationReport:
    program: str
    metrics: CalibrationMetrics
    labor_calibration_status: str
    staffing_readiness: str
    tooling_readiness: str
    overall_readiness: str
    full_rate_recommendations_enabled: bool
    blockers: tuple[str, ...]
    routing_revisions: tuple[str, ...]


@dataclass(frozen=True)
class WorkCenterLabor:
    program: str
    work_center: str
    planned_hours: Decimal
    actual_hours: Decimal


@dataclass(frozen=True)
class WorkCenterLaborRollup:
    program: str
    work_center: str
    planned_hours: Decimal
    actual_hours: Decimal
    variance_hours: Decimal
    labor_wape: Decimal | None


def _decimal(value, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CalibrationError(f"{field} must be numeric") from None
    if not result.is_finite():
        raise CalibrationError(f"{field} must be finite")
    return result


def _round(value: Decimal, places: str = "0.0001") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _next_month(value: date) -> date:
    return date(value.year + (1 if value.month == 12 else 0),
                1 if value.month == 12 else value.month + 1, 1)


def _month_sequence(start: date, end: date):
    current = _month_start(start)
    last = _month_start(end)
    while current <= last:
        yield current
        current = _next_month(current)


def _active_days(
        start: datetime, finish: datetime,
        period_start: date, period_end: date) -> int:
    active_start = max(start.date(), period_start)
    active_end = min(finish.date(), period_end)
    return max(0, (active_end - active_start).days)


def _validate_order(order: CalibrationOrder, program: str | None = None) -> None:
    if not order.order_no.strip():
        raise CalibrationError("order_no is required")
    if program is not None and order.program.upper() != program.upper():
        raise CalibrationError(
            f"program mismatch for order {order.order_no}: {order.program} != {program}")
    if order.actual_completion <= order.actual_start:
        raise CalibrationError("actual completion must follow actual start")
    if order.modeled_completion <= order.actual_start:
        raise CalibrationError("modeled completion must follow actual start")
    if (_decimal(order.planned_labor_hours, "planned_labor_hours") < 0
            or _decimal(order.actual_labor_hours, "actual_labor_hours") < 0):
        raise CalibrationError("labor hours cannot be negative")


def build_monthly_periods(
        *, orders: tuple[CalibrationOrder, ...],
        measurement_start: date, measurement_end: date,
        flow_units: tuple[CalibrationFlowUnit, ...] | None = None,
        ) -> tuple[CalibrationPeriod, ...]:
    """Reconstruct actual and modeled monthly WIP using half-open order intervals."""
    if measurement_end < measurement_start:
        raise CalibrationError("measurement_end must not precede measurement_start")
    for order in orders:
        _validate_order(order)
    flows = flow_units or tuple(CalibrationFlowUnit(
        order_no=order.order_no, program=order.program,
        actual_start=order.actual_start, actual_completion=order.actual_completion,
        modeled_completion=order.modeled_completion) for order in orders)
    horizon_end = datetime.combine(
        measurement_end + timedelta(days=1), datetime.min.time())
    for row in flows:
        if not row.order_no.strip() or row.modeled_completion <= row.actual_start:
            raise CalibrationError("invalid calibration flow interval")
        if row.actual_completion is not None and row.actual_completion <= row.actual_start:
            raise CalibrationError("actual completion must follow actual start")
    periods = []
    for month in _month_sequence(measurement_start, measurement_end):
        period_start = max(month, measurement_start)
        period_end = min(_next_month(month), horizon_end.date())
        days = (period_end - period_start).days
        actual_wip_days = sum(
            _active_days(
                row.actual_start,
                min(row.actual_completion or horizon_end, horizon_end),
                period_start,
                period_end,
            )
            for row in flows)
        modeled_wip_days = sum(
            _active_days(
                row.actual_start,
                min(row.modeled_completion, horizon_end),
                period_start,
                period_end,
            )
            for row in flows)
        periods.append(CalibrationPeriod(
            month=month,
            actual_releases=sum(
                period_start <= row.actual_start.date() < period_end for row in flows),
            actual_completions=sum(
                row.actual_completion is not None
                and period_start <= row.actual_completion.date() < period_end
                for row in flows),
            modeled_completions=sum(
                period_start <= row.modeled_completion.date() < period_end
                for row in flows),
            actual_average_wip=_round(
                Decimal(actual_wip_days) / Decimal(days)),
            modeled_average_wip=_round(
                Decimal(modeled_wip_days) / Decimal(days)),
        ))
    return tuple(periods)


def _wape(actual: list[Decimal], modeled: list[Decimal]) -> Decimal | None:
    denominator = sum((abs(value) for value in actual), Decimal(0))
    if denominator == 0:
        return None
    numerator = sum(
        (abs(expected - observed) for observed, expected in zip(actual, modeled)),
        Decimal(0),
    )
    return _round(numerator / denominator)


def _valid_readiness(value: str, field: str) -> str:
    normalized = value.upper()
    if normalized not in {"READY", "PROVISIONAL", "UNRESOLVED"}:
        raise CalibrationError(f"invalid {field}: {value}")
    return normalized


def calibrate_program(
        *, program: str, orders: tuple[CalibrationOrder, ...],
        periods: tuple[CalibrationPeriod, ...], thresholds: CalibrationThresholds,
        staffing_readiness: str, tooling_readiness: str,
        thresholds_approved: bool = True) -> ProgramCalibrationReport:
    """Score historical labor/throughput fidelity without requiring tooling readiness."""
    code = program.upper()
    for order in orders:
        _validate_order(order, code)
    if thresholds.minimum_orders <= 0:
        raise CalibrationError("minimum_orders must be positive")
    threshold_values = (
        thresholds.cycle_mae_days_max, thresholds.completion_wape_max,
        thresholds.wip_wape_max, thresholds.labor_wape_max,
    )
    if any(_decimal(value, "threshold") < 0 for value in threshold_values):
        raise CalibrationError("calibration thresholds cannot be negative")
    staffing = _valid_readiness(staffing_readiness, "staffing_readiness")
    tooling = _valid_readiness(tooling_readiness, "tooling_readiness")

    cycle_errors = [
        Decimal(str((order.modeled_completion - order.actual_completion).total_seconds()))
        / Decimal(86400)
        for order in orders
    ]
    cycle_mae = (_round(
        sum((abs(value) for value in cycle_errors), Decimal(0))
        / Decimal(len(cycle_errors)), "0.1") if cycle_errors else None)
    cycle_bias = (_round(
        sum(cycle_errors, Decimal(0)) / Decimal(len(cycle_errors)), "0.1")
                  if cycle_errors else None)
    completion_wape = _wape(
        [Decimal(row.actual_completions) for row in periods],
        [Decimal(row.modeled_completions) for row in periods])
    wip_wape = _wape(
        [row.actual_average_wip for row in periods],
        [row.modeled_average_wip for row in periods])
    labor_wape = _wape(
        [_decimal(row.actual_labor_hours, "actual_labor_hours") for row in orders],
        [_decimal(row.planned_labor_hours, "planned_labor_hours") for row in orders])
    metrics = CalibrationMetrics(
        sample_orders=len(orders), cycle_mae_days=cycle_mae,
        cycle_bias_days=cycle_bias, completion_wape=completion_wape,
        wip_wape=wip_wape, labor_wape=labor_wape)

    blockers = []
    if not thresholds_approved:
        blockers.append("THRESHOLDS_UNAPPROVED")
    if len(orders) < thresholds.minimum_orders:
        blockers.append("INSUFFICIENT_SAMPLE")
    checks = (
        ("CYCLE_MAE", cycle_mae, _decimal(
            thresholds.cycle_mae_days_max, "cycle_mae_days_max")),
        ("COMPLETION_WAPE", completion_wape, _decimal(
            thresholds.completion_wape_max, "completion_wape_max")),
        ("WIP_WAPE", wip_wape, _decimal(
            thresholds.wip_wape_max, "wip_wape_max")),
        ("LABOR_WAPE", labor_wape, _decimal(
            thresholds.labor_wape_max, "labor_wape_max")),
    )
    failed = False
    for label, value, maximum in checks:
        if value is None:
            blockers.append(f"{label}_MISSING")
        elif value > maximum:
            blockers.append(label)
            failed = True
    if failed:
        labor_status = "FAILED"
    elif ("INSUFFICIENT_SAMPLE" in blockers
          or "THRESHOLDS_UNAPPROVED" in blockers
          or any(label.endswith("_MISSING") for label in blockers)):
        labor_status = "PROVISIONAL"
    else:
        labor_status = "READY"
    if staffing != "READY":
        blockers.append(f"STAFFING_{staffing}")
    if tooling != "READY":
        blockers.append(f"TOOLING_{tooling}")
    full = labor_status == staffing == tooling == "READY"
    overall = "READY" if full else "FAILED" if labor_status == "FAILED" else "PARTIAL"
    return ProgramCalibrationReport(
        program=code, metrics=metrics,
        labor_calibration_status=labor_status,
        staffing_readiness=staffing, tooling_readiness=tooling,
        overall_readiness=overall,
        full_rate_recommendations_enabled=full,
        blockers=tuple(dict.fromkeys(blockers)),
        routing_revisions=tuple(sorted({order.routing_revision for order in orders})),
    )


def rollup_work_center_labor(
        rows: tuple[WorkCenterLabor, ...]) -> dict[tuple[str, str], WorkCenterLaborRollup]:
    grouped: dict[tuple[str, str], list[Decimal]] = {}
    for row in rows:
        key = (row.program.upper(), row.work_center)
        planned = _decimal(row.planned_hours, "planned_hours")
        actual = _decimal(row.actual_hours, "actual_hours")
        if planned < 0 or actual < 0:
            raise CalibrationError("work-center labor hours cannot be negative")
        current = grouped.setdefault(key, [Decimal(0), Decimal(0)])
        current[0] += planned
        current[1] += actual
    result = {}
    for (program, work_center), (planned, actual) in sorted(grouped.items()):
        wape = (_round(abs(planned - actual) / actual) if actual else None)
        result[(program, work_center)] = WorkCenterLaborRollup(
            program=program, work_center=work_center,
            planned_hours=planned, actual_hours=actual,
            variance_hours=actual - planned, labor_wape=wape)
    return result
