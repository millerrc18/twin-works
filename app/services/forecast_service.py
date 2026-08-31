"""Forecast orchestration: DataSource -> pooled sim -> ML residual -> P50/P80 + badge."""
from dataclasses import dataclass
from datetime import date
from app.data.source import DataSource
from app.data import rtg_targets
from app.engines.rtg_wrapper import run_pooled
from app.engines.router_registry import registry
from ml.model.registry import registry_model
from ml.model.features import FeatureBuilder
from app.services import program_service as PSVC
from app.services.planning_basis_service import (
    PlanningContext,
    comparison_target,
    configured_context,
)

_fb = FeatureBuilder()


def PROGRAMS():
    """Active program codes (registry-driven; falls back to the seed 3)."""
    return PSVC.program_order()


@dataclass
class UnitForecast:
    serial: str
    so: str
    program: str
    maxop: int | None
    milestone: str
    contract_date: date | None
    plan_target_date: date | None
    comparison_target_date: date | None
    planning_basis: str
    plan_label: str | None
    basis_effective: bool
    forecast_visibility: str
    epoch_key: str | None
    sim_finish_date: date | None
    p50_date: date | None
    p80_date: date | None
    delta_to_target: int | None
    target_coverage_issue: bool
    stalled: bool
    model_status: str


def _pooled_sim(ds: DataSource, programs=None, profile=None):
    programs = programs or PROGRAMS()
    units_by_program = {
        p: [u.as_sim_unit() for u in ds.get_wip_units(p) if not u.stalled]
        for p in programs
    }
    return run_pooled(units_by_program, ds.as_of(), profile=profile)


def forecast_program(ds: DataSource, program: str, programs=None,
                     simulation: dict | None = None,
                     planning: PlanningContext | None = None,
                     plan_targets: dict[str, date] | None = None,
                     include_hidden: bool = False) -> list[UnitForecast]:
    sim = simulation if simulation is not None else _pooled_sim(ds, programs)
    planning = planning or configured_context(program)
    spec = registry.spec(program)
    out = []
    for u in ds.get_wip_units(program):
        ms = spec.milestone_of(u.maxop)
        # per-unit features enable the TRAINED path; empirical path ignores them
        feats = _fb.build(u.serial, u.so, program, u.maxop).model_features()
        pred = registry_model.predict(program, feats)
        plan_target = None
        if planning.configured_planning_basis == "PLAN_SLOTS":
            plan_target = ((plan_targets or {}).get(u.serial)
                           if plan_targets is not None else rtg_targets.rtg_ship(u.serial))
        target = comparison_target(
            planning, contract_date=u.commit, plan_target_date=plan_target)
        coverage_issue = (planning.basis_effective
                          and planning.configured_planning_basis == "PLAN_SLOTS"
                          and plan_target is None)
        if u.stalled:
            out.append(UnitForecast(
                u.serial, u.so, program, u.maxop, ms, u.commit, plan_target, target,
                planning.configured_planning_basis, planning.plan_label,
                planning.basis_effective, planning.forecast_visibility, planning.epoch_key,
                None, None, None, None, coverage_issue, True, pred.mode))
            continue
        r = sim.get(u.serial)
        sim_fin = r["finish"].date() if r and r.get("finish") else None
        p50 = p80 = delta = None
        if sim_fin:
            p50, p80 = registry_model.apply(sim_fin, pred)
            if target:
                delta = (p50 - target).days
        if planning.forecast_visibility != "PUBLISHED" and not include_hidden:
            sim_fin = p50 = p80 = delta = None
        out.append(UnitForecast(
            u.serial, u.so, program, u.maxop, ms, u.commit, plan_target, target,
            planning.configured_planning_basis, planning.plan_label,
            planning.basis_effective, planning.forecast_visibility, planning.epoch_key,
            sim_fin, p50, p80, delta, coverage_issue, False, pred.mode))
    return out


def all_programs(ds: DataSource) -> dict:
    return {p: forecast_program(ds, p) for p in PROGRAMS()}


def program_summary(ds: DataSource, program: str, *, planning: PlanningContext | None = None,
                    plan_targets: dict[str, date] | None = None,
                    programs=None, simulation: dict | None = None) -> dict:
    planning = planning or configured_context(program)
    fc = forecast_program(
        ds, program, programs=programs, simulation=simulation,
        planning=planning, plan_targets=plan_targets)
    wip = len(fc)
    behind = sum(1 for f in fc if f.delta_to_target is not None and f.delta_to_target > 0)
    stalled = sum(1 for f in fc if f.stalled)
    pred = registry_model.predict(program)
    return dict(program=program, wip=wip, behind=behind, stalled=stalled,
                model_status=pred.mode, n_scored=pred.n_scored,
                bias_days=round(-pred.p50_days, 1),
                lifecycle_state=planning.lifecycle_state,
                planning_basis=planning.configured_planning_basis,
                plan_label=planning.plan_label, basis_effective=planning.basis_effective,
                forecast_visibility=planning.forecast_visibility, epoch_key=planning.epoch_key,
                target_coverage_issues=sum(1 for f in fc if f.target_coverage_issue))
