"""Read-only work-center load metrics shared by Levers and the Factory Map."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import routers as R
from app.engines import rtg_wrapper as WRAPPER
from app.engines.router_registry import registry


def scheduled_work_center_loads(units_by_program: dict, as_of: datetime,
                                display_programs: set[str] | None = None,
                                simulation: dict | None = None) -> dict[str, dict]:
    """Return modeled WC demand without changing the simulator or any capacity setting.

    All supplied programs remain in the baseline simulation so shared-resource contention is
    preserved. ``display_programs`` only scopes the activity attributed to the caller.
    """
    display_programs = set(display_programs or units_by_program)
    results = simulation if simulation is not None else WRAPPER.run_pooled(units_by_program, as_of)
    op_by_program = {
        program: {op[0]: (op[2], float(op[3])) for op in registry.ops(program)}
        for program in units_by_program
        if program in registry.programs
    }
    program_of = {
        unit["serial"]: program
        for program, units in units_by_program.items()
        for unit in units
    }
    metrics = defaultdict(lambda: {
        "demand_by_week": defaultdict(float),
        "scheduled_labor_hours_7d": 0.0,
        "scheduled_unit_keys": set(),
    })
    horizon = as_of + timedelta(days=7)
    for serial, result in results.items():
        program = program_of.get(serial)
        if program not in display_programs:
            continue
        for opno, start in result.get("op_dt", {}).items():
            wc, hours = op_by_program.get(program, {}).get(opno, (None, 0.0))
            if not wc:
                continue
            row = metrics[wc]
            row["demand_by_week"][start.isocalendar()[:2]] += hours
            if as_of <= start < horizon:
                row["scheduled_labor_hours_7d"] += hours
            row["scheduled_unit_keys"].add((program, serial))
    return metrics


def modeled_weekly_capacity(wc: str, programs: set[str] | None = None) -> float | None:
    """Read the capacity profile currently supplied to the simulation for one WC."""
    programs = set(programs or registry.programs)
    profile = WRAPPER.simulation_profile()
    configured = [
        shifts for (program, budget_wc), shifts in profile["shift_budgets"].items()
        if program in programs and budget_wc == wc
    ]
    if configured:
        return round(sum(sum(shifts.values()) * 5 for shifts in configured), 1)
    used = [
        program for program in programs
        if program in registry.programs and any(op[2] == wc for op in registry.ops(program))
    ]
    if not used:
        return None
    # The scheduler gives an unknown shared resource a single default pool, not one pool/program.
    multiplier = 1 if wc in profile["shared_wcs"] else len(used)
    return round(sum(R.DEFAULT_SHIFT.values()) * 5 * multiplier, 1)


def work_center_load_rows(units_by_program: dict, as_of: datetime,
                          display_programs: set[str] | None = None,
                          work_centers: set[str] | None = None,
                          simulation: dict | None = None) -> dict[str, dict]:
    """Combine scheduled demand and configured capacity into map-ready telemetry."""
    display_programs = set(display_programs or units_by_program)
    demand = scheduled_work_center_loads(
        units_by_program, as_of, display_programs, simulation=simulation,
    )
    known = set(demand)
    for program in display_programs:
        if program in registry.programs:
            known.update(op[2] for op in registry.ops(program))
    if work_centers is not None:
        known.update(work_centers)

    rows = {}
    for wc in known:
        item = demand.get(wc, {})
        weeks = item.get("demand_by_week", {})
        capacity = modeled_weekly_capacity(wc, set(units_by_program))
        peak = max(weeks.values()) if weeks else 0.0
        rows[wc] = {
            "wc": wc,
            "modeled_weekly_capacity_hours": capacity,
            "peak_weekly_demand_hours": round(peak, 1),
            "peak_weekly_utilization_pct": round(100 * peak / capacity) if capacity else None,
            "weeks_over_capacity": sum(1 for value in weeks.values() if capacity and value > capacity),
            "scheduled_labor_hours_7d": round(item.get("scheduled_labor_hours_7d", 0.0), 1),
            "scheduled_unit_count": len(item.get("scheduled_unit_keys", set())),
        }
    return rows
