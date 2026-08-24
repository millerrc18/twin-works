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
    commit: date | None
    sim_finish: date | None
    p50: date | None
    p80: date | None
    delta_contract: int | None   # p50 vs contract (days; + = late)
    stalled: bool
    model_status: str


def _pooled_sim(ds: DataSource):
    units_by_program = {
        p: [u.as_sim_unit() for u in ds.get_wip_units(p) if not u.stalled]
        for p in PROGRAMS()
    }
    return run_pooled(units_by_program, ds.as_of())


def forecast_program(ds: DataSource, program: str) -> list[UnitForecast]:
    sim = _pooled_sim(ds)
    spec = registry.spec(program)
    out = []
    for u in ds.get_wip_units(program):
        ms = spec.milestone_of(u.maxop)
        # per-unit features enable the TRAINED path; empirical path ignores them
        feats = _fb.build(u.serial, u.so, program, u.maxop).model_features()
        pred = registry_model.predict(program, feats)
        if u.stalled:
            out.append(UnitForecast(u.serial, u.so, program, u.maxop, ms, u.commit,
                                    None, None, None, None, True, pred.mode))
            continue
        r = sim.get(u.serial)
        sim_fin = r["finish"].date() if r and r.get("finish") else None
        # target = RTG ship if the unit has an RTG plan, else contract (Aegis)
        target = rtg_targets.rtg_ship(u.serial) or u.commit
        p50 = p80 = delta = None
        if sim_fin:
            p50, p80 = registry_model.apply(sim_fin, pred)
            if target:
                delta = (p50 - target).days
        out.append(UnitForecast(u.serial, u.so, program, u.maxop, ms, target,
                                sim_fin, p50, p80, delta, False, pred.mode))
    return out


def all_programs(ds: DataSource) -> dict:
    return {p: forecast_program(ds, p) for p in PROGRAMS()}


def program_summary(ds: DataSource, program: str) -> dict:
    fc = forecast_program(ds, program)
    wip = len(fc)
    behind = sum(1 for f in fc if f.delta_contract is not None and f.delta_contract > 0)
    stalled = sum(1 for f in fc if f.stalled)
    pred = registry_model.predict(program)
    return dict(program=program, wip=wip, behind=behind, stalled=stalled,
                model_status=pred.mode, n_scored=pred.n_scored,
                bias_days=round(-pred.p50_days, 1))
