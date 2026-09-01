"""Portfolio and program-workspace read models."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.router_registry import registry
from app.engines import rtg_wrapper
from app.models import (
    AssumptionReview,
    ModelEpoch,
    ModelEpochTransition,
    OperationResourceBinding,
    PositionState,
    ProgramEpochActivation,
    SyncRun,
)
from app.services import forecast_service as FORECASTS
from app.services import model_epoch_service as EPOCHS
from app.services import planning_basis_service as PLANNING
from app.services import program_service as PROGRAMS
from app.services import resource_explain as RESOURCES
from app.services.capacity_metrics import work_center_load_rows
from app.services.observation_quarantine import active_quarantines


WORKSPACE_TABS = (
    ("overview", "Overview"),
    ("schedule", "Schedule"),
    ("flow", "Flow"),
    ("units", "Units"),
    ("resources", "Resources"),
    ("assumptions", "Assumptions"),
    ("history", "History"),
)


def _current_operation(program: str, maxop: int | None):
    operations = registry.ops(program)
    return next((row for row in operations if maxop is None or row[0] > maxop), None)


def _freshness_label(value: datetime | None, as_of: date) -> tuple[str, str]:
    if value is None:
        return "No sync evidence", "missing"
    observed = value.date()
    age = max(0, (as_of - observed).days)
    if age == 0:
        return "Today", "current"
    if age == 1:
        return "1 day", "current"
    if age <= 3:
        return f"{age} days", "aging"
    return f"{age} days", "stale"


def _basis_display(planning) -> str:
    if planning.configured_planning_basis == "PLAN_SLOTS":
        return f"{planning.target_label} plan"
    if planning.configured_planning_basis == "CONTRACT_DATES":
        return planning.target_label or "Contract"
    return "No approved target"


def _next_gate(state: str, readiness: str) -> str:
    if state == "DRAFT":
        return "Complete configuration and begin observation"
    if state == "OBSERVE":
        if readiness == "INCOMPLETE":
            return "Resolve missing evidence and resource bindings"
        return "IE / floor acceptance for provisional analysis"
    if state == "PROVISIONAL":
        return "Program scheduling approval for publication"
    if state == "PAUSED":
        return "Resolve pause rationale and return to observation"
    if state in {"ARCHIVED", "DEPRECATED"}:
        return "Historical record"
    return "Continue governed monitoring"


async def _position_freshness(db: AsyncSession) -> dict[str, datetime]:
    rows = (await db.execute(
        select(PositionState.program, func.max(PositionState.synced_at))
        .group_by(PositionState.program)
    )).all()
    return {program: synced_at for program, synced_at in rows}


async def build_portfolio(db: AsyncSession, ds) -> dict:
    """Build the portfolio console with one simulation and one resource aggregation."""
    codes = [code for code in PROGRAMS.program_order() if code in registry.programs]
    published_codes = await PLANNING.published_programs(db, codes)
    simulation = FORECASTS._pooled_sim(ds, published_codes) if published_codes else {}
    published_units = {
        code: [unit.as_sim_unit() for unit in ds.get_wip_units(code) if not unit.stalled]
        for code in published_codes
    }
    capacity = work_center_load_rows(
        published_units, ds.as_of(), simulation=simulation,
    ) if published_units else {}
    shared_rows = [row for wc, row in capacity.items() if wc in rtg_wrapper.shared_wcs()]
    pressure_over = sum(
        (row.get("peak_weekly_utilization_pct") or 0) > 100 for row in shared_rows)
    pressure_near = sum(
        85 <= (row.get("peak_weekly_utilization_pct") or 0) <= 100 for row in shared_rows)
    freshness = await _position_freshness(db)
    latest_sync = await db.scalar(
        select(SyncRun).where(SyncRun.stage == "done")
        .order_by(SyncRun.finished_at.desc(), SyncRun.id.desc()).limit(1)
    )
    open_reviews = int(await db.scalar(select(func.count(AssumptionReview.id)).where(
        AssumptionReview.status == "OPEN")) or 0)
    quarantine_count = len(await active_quarantines(db, "BCALAY"))

    rows = []
    maturity = []
    rtg_late = rtg_denominator = 0
    contract_late = contract_denominator = 0
    total_wip = total_stalled = coverage_debt = 0
    commitment_ready = 0

    for code in codes:
        planning = await PLANNING.context_for_program(db, code)
        units = ds.get_wip_units(code)
        plan_targets = None
        if planning.configured_planning_basis == "PLAN_SLOTS":
            from app.services import slot_service
            slots = await slot_service.get_slots(db, code, {unit.serial for unit in units})
            plan_targets = {slot.serial: slot.target_date for slot in slots if slot.serial}
        forecasts = FORECASTS.forecast_program(
            ds, code, programs=published_codes, simulation=simulation,
            planning=planning, plan_targets=plan_targets,
        )
        eligible = [row for row in forecasts
                    if not row.stalled and row.comparison_target_date and row.p50_date]
        late = sum(row.p50_date > row.comparison_target_date for row in eligible)
        if planning.basis_effective and planning.configured_planning_basis == "PLAN_SLOTS":
            rtg_late += late
            rtg_denominator += len(eligible)
        elif planning.basis_effective and planning.configured_planning_basis == "CONTRACT_DATES":
            contract_late += late
            contract_denominator += len(eligible)

        readiness = await RESOURCES.program_readiness(db, code, ds.as_of().date())
        route_wcs = {op[2] for op in registry.ops(code) if op[2]}
        resource_candidates = [capacity[wc] for wc in route_wcs if wc in capacity]
        pressure = max(
            resource_candidates,
            key=lambda item: item.get("peak_weekly_utilization_pct") or -1,
            default=None,
        )
        active_wcs = Counter()
        for unit in units:
            if unit.stalled:
                continue
            current = _current_operation(code, unit.maxop)
            if current:
                active_wcs[current[2]] += 1
        dominant_wc = active_wcs.most_common(1)[0] if active_wcs else None
        fresh_label, fresh_state = _freshness_label(freshness.get(code), ds.as_of().date())
        published = await EPOCHS.published_epoch(db, code)
        latest = await EPOCHS.latest_epoch(db, code)
        candidate = latest if latest and (not published or latest.epoch.id != published.epoch.id) else None

        row = {
            "code": code,
            "name": PROGRAMS.name(code),
            "lifecycle": planning.lifecycle_state,
            "basis": planning.configured_planning_basis,
            "basis_label": _basis_display(planning),
            "basis_effective": planning.basis_effective,
            "plan_source": planning.plan_source,
            "plan_version": planning.plan_version,
            "wip": len(units),
            "stalled": sum(unit.stalled for unit in units),
            "risk": late if planning.basis_effective else None,
            "risk_denominator": len(eligible) if planning.basis_effective else None,
            "readiness": readiness["readiness"],
            "issue_count": len(readiness["issues"]),
            "dominant_wc": dominant_wc[0] if dominant_wc else None,
            "dominant_wc_units": dominant_wc[1] if dominant_wc else 0,
            "pressure_wc": pressure["wc"] if pressure else None,
            "pressure_pct": pressure.get("peak_weekly_utilization_pct") if pressure else None,
            "freshness": fresh_label,
            "freshness_state": fresh_state,
            "epoch_key": planning.epoch_key,
            "published_epoch": published.epoch.epoch_key if published else None,
            "candidate_epoch": candidate.epoch.epoch_key if candidate else None,
            "candidate_state": candidate.state if candidate else None,
        }
        rows.append(row)
        total_wip += row["wip"]
        total_stalled += row["stalled"]
        coverage_debt += row["issue_count"]
        commitment_ready += int(planning.forecast_visibility == "PUBLISHED")
        if candidate or planning.forecast_visibility != "PUBLISHED":
            state = candidate.state if candidate else planning.lifecycle_state
            maturity.append({
                **row,
                "candidate_state": state,
                "next_gate": _next_gate(state, readiness["readiness"]),
            })

    return {
        "programs": rows,
        "maturity": maturity,
        "total_wip": total_wip,
        "total_stalled": total_stalled,
        "rtg_late": rtg_late,
        "rtg_denominator": rtg_denominator,
        "contract_late": contract_late,
        "contract_denominator": contract_denominator,
        "commitment_ready": commitment_ready,
        "program_count": len(codes),
        "open_reviews": open_reviews,
        "coverage_debt": coverage_debt,
        "quarantine_count": quarantine_count,
        "pressure_over": pressure_over,
        "pressure_near": pressure_near,
        "latest_sync": latest_sync.finished_at if latest_sync else None,
        "as_of": ds.as_of(),
    }


async def build_program_workspace(db: AsyncSession, ds, program: str, tab: str) -> dict:
    """Build one lifecycle-safe workspace tab."""
    program = program.upper()
    if program not in registry.programs:
        raise KeyError(program)
    planning = await PLANNING.context_for_program(db, program)
    readiness = await RESOURCES.program_readiness(db, program, ds.as_of().date())
    units = ds.get_wip_units(program)
    state_rows = (await db.execute(select(PositionState).where(
        PositionState.program == program,
        PositionState.closed.is_(None),
    ))).scalars().all()
    state_by_so = {row.so: row for row in state_rows}
    unit_rows = []
    phase_counts = Counter()
    wc_counts = Counter()
    for unit in units:
        current = _current_operation(program, unit.maxop)
        phase = registry.spec(program).milestone_of(unit.maxop)
        phase_counts[phase or "Unpositioned"] += 1
        if current:
            wc_counts[current[2]] += 1
        source = state_by_so.get(unit.so)
        unit_rows.append({
            "serial": unit.serial,
            "so": unit.so,
            "maxop": unit.maxop,
            "phase": phase,
            "current_op": current[0] if current else None,
            "current_operation": current[1] if current else "Route complete",
            "current_wc": current[2] if current else None,
            "contract_date": unit.commit,
            "stalled": unit.stalled,
            "last_clock": source.last_clock if source else None,
            "synced_at": source.synced_at if source else None,
        })
    unit_rows.sort(key=lambda row: (not row["stalled"], row["contract_date"] or date.max,
                                    row["serial"]))
    flow = [
        {"code": code, "name": name, "count": phase_counts.get(code, 0)}
        for code, name in registry.spec(program).milestones
    ]
    if phase_counts.get("Unpositioned"):
        flow.append({"code": "UNPOSITIONED", "name": "Unpositioned",
                     "count": phase_counts["Unpositioned"]})

    bindings = (await db.execute(select(OperationResourceBinding).where(
        OperationResourceBinding.program == program,
        OperationResourceBinding.status == "APPROVED",
    ))).scalars().all()
    bound_by_wc = Counter()
    for binding in bindings:
        current = next((op for op in registry.ops(program) if op[0] == binding.acquire_op), None)
        if current:
            bound_by_wc[current[2]] += 1
    issue_by_wc = {}
    for issue in readiness["issues"]:
        issue_by_wc.setdefault(issue["subject_key"], []).append(issue)
    resources = []
    for wc in sorted({op[2] for op in registry.ops(program) if op[2]}):
        operations = [op[0] for op in registry.ops(program) if op[2] == wc]
        resources.append({
            "wc": wc,
            "operation_count": len(operations),
            "operations": operations,
            "active_units": wc_counts.get(wc, 0),
            "binding_count": bound_by_wc.get(wc, 0),
            "issues": issue_by_wc.get(wc, []),
            "readiness": "INCOMPLETE" if issue_by_wc.get(wc) else "COMPLETE",
        })

    epochs = (await db.execute(select(ModelEpoch).where(
        ModelEpoch.program == program).order_by(ModelEpoch.id.desc()))).scalars().all()
    epoch_ids = [epoch.id for epoch in epochs]
    transitions = (await db.execute(select(ModelEpochTransition).where(
        ModelEpochTransition.epoch_id.in_(epoch_ids)
    ).order_by(ModelEpochTransition.transitioned_at.desc()))).scalars().all() if epoch_ids else []
    transition_by_epoch = {}
    for transition in transitions:
        transition_by_epoch.setdefault(transition.epoch_id, []).append(transition)
    activations = (await db.execute(select(ProgramEpochActivation).where(
        ProgramEpochActivation.program == program
    ).order_by(ProgramEpochActivation.activated_at.desc()))).scalars().all()
    activation_by_epoch = {activation.epoch_id: activation for activation in activations}
    effective_publication = await EPOCHS.published_epoch(db, program)
    effective_epoch_id = effective_publication.epoch.id if effective_publication else None
    history = [{
        "epoch_key": epoch.epoch_key,
        "label": epoch.label,
        "kind": epoch.epoch_kind,
        "resource_mode": epoch.resource_mode,
        "created_at": epoch.created_at,
        "state": transition_by_epoch[epoch.id][0].to_state,
        "published": epoch.id == effective_epoch_id,
        "was_published": epoch.id in activation_by_epoch,
        "transitions": transition_by_epoch.get(epoch.id, []),
    } for epoch in epochs]

    published_codes = await PLANNING.published_programs(db, PROGRAMS.program_order())
    simulation = FORECASTS._pooled_sim(ds, published_codes) if planning.basis_effective else {}
    plan_targets = None
    if planning.configured_planning_basis == "PLAN_SLOTS":
        from app.services import slot_service
        slots = await slot_service.get_slots(db, program, {unit.serial for unit in units})
        plan_targets = {slot.serial: slot.target_date for slot in slots if slot.serial}
    forecast_rows = FORECASTS.forecast_program(
        ds, program, programs=published_codes, simulation=simulation,
        planning=planning, plan_targets=plan_targets,
    )
    eligible = [row for row in forecast_rows
                if row.p50_date and row.comparison_target_date and not row.stalled]
    fresh = max((row.synced_at for row in state_rows), default=None)
    fresh_label, fresh_state = _freshness_label(fresh, ds.as_of().date())
    return {
        "program": program,
        "program_name": PROGRAMS.name(program),
        "tab": tab,
        "tabs": WORKSPACE_TABS,
        "planning": planning,
        "readiness": readiness,
        "wip": len(units),
        "stalled": sum(unit.stalled for unit in units),
        "risk": sum(row.p50_date > row.comparison_target_date for row in eligible),
        "risk_denominator": len(eligible),
        "freshness": fresh_label,
        "freshness_state": fresh_state,
        "unit_rows": unit_rows,
        "flow": flow,
        "work_centers": [{"wc": wc, "count": count}
                         for wc, count in wc_counts.most_common()],
        "resources": resources,
        "history": history,
        "next_gate": _next_gate(planning.lifecycle_state, readiness["readiness"]),
    }
