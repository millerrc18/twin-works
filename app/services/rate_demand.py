"""RATE-01b demand netting and governed external-load integration."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResourcePool
from app.services.rate_readiness import (
    SyntheticRelease,
    WorkingCalendar,
    releases_as_sim_units,
    working_days,
)


class RateDemandError(ValueError):
    """Demand cannot be integrated without ambiguity or double counting."""


@dataclass(frozen=True)
class DemandRecord:
    demand_key: str
    program: str
    variant: str
    release_month: date
    quantity: Decimal
    order_no: str | None = None


@dataclass(frozen=True)
class WipIdentity:
    program: str
    order_no: str
    variant: str
    represented_quantity: Decimal = Decimal("1")


@dataclass(frozen=True)
class NettedDemandRow:
    demand_key: str
    program: str
    variant: str
    release_month: date
    gross_quantity: Decimal
    net_quantity: Decimal
    order_no: str | None


@dataclass(frozen=True)
class DemandExclusion:
    demand_key: str
    excluded_quantity: Decimal
    reason: str
    order_no: str | None


@dataclass(frozen=True)
class NettedDemand:
    rows: tuple[NettedDemandRow, ...]
    exclusions: tuple[DemandExclusion, ...]


@dataclass(frozen=True)
class CombinedUnitDemand:
    units_by_program: dict[str, list[dict]]
    inherited_unit_count: int
    synthetic_unit_count: int


@dataclass(frozen=True)
class ExternalRateDemand:
    snapshot_id: int
    hours_by_pool_shift_month: dict[tuple[int, int, date], Decimal]
    hours_by_pool_code_month: dict[tuple[str, date], Decimal]
    included_rows: int
    excluded_rows: int
    readiness: str
    readiness_reasons: tuple[str, ...]


def _decimal(value, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RateDemandError(f"{field} must be numeric") from None
    if not result.is_finite():
        raise RateDemandError(f"{field} must be finite")
    return result


def _month(value: date) -> date:
    return date(value.year, value.month, 1)


def net_customer_demand(
        *, records: tuple[DemandRecord, ...], wip: tuple[WipIdentity, ...],
        active_programs: set[str]) -> NettedDemand:
    """Subtract only demand quantities explicitly represented by tracked WIP identities."""
    active = {program.upper() for program in active_programs}
    keys = [record.demand_key for record in records]
    if len(keys) != len(set(keys)):
        raise RateDemandError("duplicate demand key")

    wip_by_order: dict[str, tuple[str, Decimal]] = {}
    for item in wip:
        program = item.program.upper()
        order_no = str(item.order_no).strip()
        quantity = _decimal(item.represented_quantity, "represented_quantity")
        if not order_no or quantity <= 0:
            raise RateDemandError("WIP identity requires a positive represented quantity")
        existing = wip_by_order.get(order_no)
        if existing and existing[0] != program:
            raise RateDemandError(
                f"WIP order {order_no} belongs to multiple programs")
        wip_by_order[order_no] = (program, (existing[1] if existing else Decimal(0)) + quantity)

    remaining_by_order = dict(wip_by_order)
    rows = []
    exclusions = []
    for record in sorted(
            records, key=lambda row: (row.release_month, row.program, row.demand_key)):
        program = record.program.upper()
        if program not in active:
            raise RateDemandError(f"inactive program {program}")
        quantity = _decimal(record.quantity, "quantity")
        if quantity <= 0:
            raise RateDemandError("demand quantity must be positive")
        if record.release_month.day != 1:
            raise RateDemandError("release_month must be the first day of a month")
        order_no = str(record.order_no).strip() if record.order_no else None
        excluded = Decimal(0)
        if order_no and order_no in remaining_by_order:
            wip_program, represented = remaining_by_order[order_no]
            if wip_program != program:
                raise RateDemandError(
                    f"demand order {order_no} belongs to {wip_program}, not {program}")
            excluded = min(quantity, represented)
            remaining_by_order[order_no] = (wip_program, represented - excluded)
        net = quantity - excluded
        if excluded:
            exclusions.append(DemandExclusion(
                demand_key=record.demand_key,
                excluded_quantity=excluded,
                reason="REPRESENTED_BY_TRACKED_WIP",
                order_no=order_no,
            ))
        if net:
            rows.append(NettedDemandRow(
                demand_key=record.demand_key,
                program=program,
                variant=record.variant,
                release_month=record.release_month,
                gross_quantity=quantity,
                net_quantity=net,
                order_no=order_no,
            ))
    return NettedDemand(rows=tuple(rows), exclusions=tuple(exclusions))


def combine_unit_demand(
        *, inherited_wip: dict[str, list[dict]],
        releases: tuple[SyntheticRelease, ...],
        active_programs: set[str],
        required_shared_programs: set[str] | None = None) -> CombinedUnitDemand:
    """Combine inherited portfolio WIP and scenario releases without mutating either source."""
    active = {program.upper() for program in active_programs}
    required = {program.upper() for program in (required_shared_programs or ())}
    missing = required - {program.upper() for program in inherited_wip}
    if missing:
        raise RateDemandError(
            f"missing required shared-program WIP: {sorted(missing)}")
    units = {program: [] for program in sorted(active)}
    inherited_count = 0
    for program, rows in inherited_wip.items():
        code = program.upper()
        if code not in active:
            raise RateDemandError(f"inherited WIP includes inactive program {code}")
        for row in rows:
            if str(row.get("program", "")).upper() != code:
                raise RateDemandError(f"WIP row program does not match {code}")
            units[code].append(deepcopy(row))
            inherited_count += 1
    synthetic = releases_as_sim_units(releases)
    for row in synthetic:
        program = row["program"].upper()
        if program not in active:
            raise RateDemandError(f"synthetic demand includes inactive program {program}")
        units[program].append(row)
    return CombinedUnitDemand(
        units_by_program=units,
        inherited_unit_count=inherited_count,
        synthetic_unit_count=len(synthetic),
    )


def build_netted_release_calendar(
        scenario_key: str, netted: NettedDemand,
        working_calendar: WorkingCalendar) -> tuple[SyntheticRelease, ...]:
    """Convert net customer quantities into deterministic scenario-only releases."""
    releases = []
    for row in netted.rows:
        integral = row.net_quantity.to_integral_value(rounding=ROUND_FLOOR)
        if row.net_quantity != integral:
            raise RateDemandError(
                f"demand {row.demand_key} has fractional discrete-unit quantity")
        quantity = int(integral)
        days = working_days(row.release_month, working_calendar)
        if quantity and not days:
            raise RateDemandError(f"no working days in {row.release_month.isoformat()}")
        for index in range(quantity):
            release_date = days[(index * len(days)) // quantity]
            releases.append(SyntheticRelease(
                scenario_unit_id=(
                    f"RATE:{scenario_key}:{row.program}:{row.demand_key}:{index + 1:05d}"),
                program=row.program,
                variant=row.variant,
                release_date=release_date,
            ))
    return tuple(releases)


async def load_external_rate_demand(
        db: AsyncSession, snapshot_id: int, *, as_of: date,
        horizon_end: date) -> ExternalRateDemand:
    """Fold one immutable external snapshot into weighted monthly pool demand."""
    from app.services.external_load_governance import assess_external_snapshot

    assessment = await assess_external_snapshot(
        db, snapshot_id, as_of=as_of, horizon_end=horizon_end)
    hours: dict[tuple[int, int, date], Decimal] = {}
    pool_hours: dict[tuple[str, date], Decimal] = {}
    included = excluded = suspect = 0
    pool_ids = {int(row["pool_id"]) for row in assessment.payload["rows"]}
    pools = (await db.execute(select(ResourcePool).where(
        ResourcePool.id.in_(pool_ids)))).scalars().all() if pool_ids else []
    codes = {pool.id: pool.code for pool in pools}
    missing_pools = pool_ids - set(codes)
    if missing_pools:
        raise RateDemandError(
            f"external demand references missing pools: {sorted(missing_pools)}")
    for row in assessment.payload["rows"]:
        if (row.get("exclusion_reason") or row.get("quality") == "EXCLUDED"
                or row.get("source_type") == "TRACKED_PROJECT"):
            excluded += 1
            continue
        if row.get("load_type") != "LABOR":
            excluded += 1
            continue
        quality = row.get("quality")
        if quality not in {"OK", "SUSPECT"}:
            excluded += 1
            continue
        if quality == "SUSPECT":
            suspect += 1
        key = (
            int(row["pool_id"]),
            int(row.get("shift") or 0),
            _month(date.fromisoformat(row["work_date"])),
        )
        weighted = _decimal(row.get("hours", 0), "external hours") * _decimal(
            row.get("weight", 1), "external weight")
        hours[key] = hours.get(key, Decimal(0)) + weighted
        code_key = (codes[key[0]], key[2])
        pool_hours[code_key] = pool_hours.get(code_key, Decimal(0)) + weighted
        included += 1

    reasons = {issue.parameter.upper() for issue in assessment.issues}
    if suspect:
        reasons.add("SUSPECT_ROWS")
    unresolved = any(issue.severity == "MISSING" for issue in assessment.issues)
    readiness = "UNRESOLVED" if unresolved else "PROVISIONAL" if reasons else "READY"
    return ExternalRateDemand(
        snapshot_id=snapshot_id,
        hours_by_pool_shift_month=dict(sorted(hours.items())),
        hours_by_pool_code_month=dict(sorted(pool_hours.items())),
        included_rows=included,
        excluded_rows=excluded,
        readiness=readiness,
        readiness_reasons=tuple(sorted(reasons)),
    )
