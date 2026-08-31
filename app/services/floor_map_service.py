"""Presentation model for the read-only Marion virtual factory."""
from __future__ import annotations

from collections import defaultdict

from app.data.floor_map import FacilityMap, load_facility_map
from app.data.source import DataSource
from app.engines import rtg_wrapper as WRAPPER
from app.engines.router_registry import registry
from app.services import forecast_service as FS
from app.services import program_service as PSVC
from app.services.capacity_metrics import work_center_load_rows


def _remaining_ops(program: str, maxop: int | None) -> list[tuple]:
    return [op for op in registry.ops(program) if maxop is None or op[0] > maxop]


def _status(relevant: bool, active: int, queued: int, late: int, at_risk: int,
            utilization: int | None) -> str:
    if not relevant:
        return "quiet"
    if late or (utilization is not None and utilization > 100):
        return "critical"
    if at_risk or (utilization is not None and utilization >= 85):
        return "warning"
    if active or queued:
        return "working"
    return "neutral"


def _unit_payload(unit, forecast, current_op: tuple | None) -> dict:
    return {
        "program": unit.program,
        "program_name": PSVC.name(unit.program),
        "serial": unit.serial,
        "so": unit.so,
        "current_operation": None if current_op is None else {
            "opno": current_op[0], "description": current_op[1], "wc": current_op[2],
        },
        "target": forecast.comparison_target_date if forecast else unit.commit,
        "p50": forecast.p50_date if forecast else None,
        "p80": forecast.p80_date if forecast else None,
        "delta_days": forecast.delta_to_target if forecast else None,
        "stalled": unit.stalled,
    }


def _resource_payload(resource: dict, metrics: dict, activity: dict, affected: list[dict],
                      relevant_wcs: set[str], catalog: dict) -> dict:
    wc = resource["wc"]
    load = metrics.get(wc, {})
    active = activity[wc]["active"]
    queued = activity[wc]["queued"]
    late = sum(1 for unit in affected if unit["delta_days"] is not None and unit["delta_days"] > 0)
    at_risk = sum(
        1 for unit in affected
        if unit["delta_days"] is not None and unit["delta_days"] <= 0
        and unit["p80"] and unit["target"] and unit["p80"] > unit["target"]
    )
    utilization = load.get("peak_weekly_utilization_pct")
    return dict(resource, catalog=catalog.get(wc, {}), is_relevant=wc in relevant_wcs,
                telemetry={
                    "active_unit_count": active,
                    "queued_unit_count": queued,
                    "scheduled_labor_hours_7d": load.get("scheduled_labor_hours_7d", 0.0),
                    "modeled_weekly_capacity_hours": load.get("modeled_weekly_capacity_hours"),
                    "peak_weekly_demand_hours": load.get("peak_weekly_demand_hours", 0.0),
                    "peak_weekly_utilization_pct": utilization,
                    "weeks_over_capacity": load.get("weeks_over_capacity", 0),
                    "late_unit_count": late,
                    "at_risk_unit_count": at_risk,
                    "status": _status(wc in relevant_wcs, active, queued, late, at_risk, utilization),
                    "sources": ["Modeled schedule", "Configured capacity", "IFS/snapshot WIP position"],
                }, affected_units=sorted(
                    affected,
                    key=lambda unit: (unit["stalled"], -(unit["delta_days"] or 0), unit["serial"]),
                ))


def build_floor_map(ds: DataSource, program: str = "all", floor_id: str | None = None,
                    simulation_programs: list[str] | None = None) -> dict:
    """Build one visual-only page model. No persisted state or forecast input is changed."""
    facility: FacilityMap = load_facility_map()
    all_programs = [code for code in PSVC.program_order() if code in registry.programs]
    requested = program.upper()
    display_programs = set(all_programs if requested == "ALL" else [requested])
    if not display_programs or not display_programs.issubset(set(all_programs)):
        raise ValueError("Unknown active program filter")

    simulation_programs = list(simulation_programs or all_programs)
    units_by_program = {
        code: [unit.as_sim_unit() for unit in ds.get_wip_units(code) if not unit.stalled]
        for code in simulation_programs
    }
    simulation = WRAPPER.run_pooled(units_by_program, ds.as_of())
    all_mapped_wcs = {placement["wc"] for placement in facility.placements}
    all_mapped_wcs.update(resource["wc"] for resource in facility.resources)
    metrics = work_center_load_rows(
        units_by_program, ds.as_of(), display_programs, all_mapped_wcs,
        simulation=simulation,
    )

    forecasts = {}
    for code in simulation_programs:
        for forecast in FS.forecast_program(
            ds, code, programs=all_programs, simulation=simulation,
        ):
            forecasts[(code, forecast.serial)] = forecast

    activity = defaultdict(lambda: {"active": 0, "queued": 0})
    affected = defaultdict(list)
    relevant_wcs: set[str] = set()
    for code in display_programs:
        for unit in ds.get_wip_units(code):
            remaining = _remaining_ops(code, unit.maxop)
            current = remaining[0] if remaining else None
            unit_wcs = list(dict.fromkeys(op[2] for op in remaining if op[2]))
            later_wcs = set(op[2] for op in remaining[1:] if op[2])
            relevant_wcs.update(unit_wcs)
            payload = _unit_payload(unit, forecasts.get((code, unit.serial)), current)
            for wc in unit_wcs:
                affected[wc].append(payload)
            if not unit.stalled:
                if current:
                    activity[current[2]]["active"] += 1
                for wc in later_wcs:
                    activity[wc]["queued"] += 1

    markers = [
        _resource_payload(placement, metrics, activity, affected[placement["wc"]], relevant_wcs, facility.catalog)
        for placement in facility.placements
    ]
    floors = []
    for item in facility.floors.values():
        floors.append(dict(item, markers=[marker for marker in markers if marker["floor_id"] == item["id"]]))
    selected_floor = floor_id if floor_id in facility.floors else floors[0]["id"]
    non_point = [
        _resource_payload(resource, metrics, activity, affected[resource["wc"]], relevant_wcs, facility.catalog)
        for resource in facility.resources
    ]
    return {
        "facility": facility,
        "generated_at": ds.as_of(),
        "program": "all" if requested == "ALL" else requested,
        "programs": [(code, PSVC.name(code)) for code in all_programs],
        "floors": floors,
        "selected_floor": selected_floor,
        "mobile_resources": [item for item in non_point if item["resource_kind"] == "mobile"],
        "unplaced_resources": [item for item in non_point if item["resource_kind"] == "unplaced"],
    }


def find_resource(model: dict, wc: str) -> dict | None:
    """Find a marker or non-point resource in an already-built map model."""
    for floor in model["floors"]:
        for marker in floor["markers"]:
            if marker["wc"] == wc:
                return marker
    for resource in model["mobile_resources"] + model["unplaced_resources"]:
        if resource["wc"] == wc:
            return resource
    return None
