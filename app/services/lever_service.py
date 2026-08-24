"""Lever service — wraps lever_engine for the web layer."""
from app.data.source import DataSource
from app.engines.lever_engine import run_lever, bottleneck_load, back_solve, LeverSpec
from app.engines.router_registry import registry
from ml.model.registry import registry_model
from ml.model.features import FeatureBuilder
from app.services import program_service as PSVC

_fb = FeatureBuilder()
# binding WC per program (the throttle a back-solve should relax)
BINDING_WC = {"ELEV": "32684", "RAD": "AEROA", "AEGIS": "221"}

# preset levers the PM can try (label -> spec factory). Keeps the UI to real, meaningful knobs.
PRESETS = {
    "paint_20": ("+20% paint capacity (WC221)", lambda: LeverSpec(wc_budget_global={"221": 1.20}, label="+20% paint (WC221)")),
    "paint_50": ("+50% paint capacity (WC221)", lambda: LeverSpec(wc_budget_global={"221": 1.50}, label="+50% paint (WC221)")),
    "assy_50":  ("+50% elevator main assembly (WC32684)", lambda: LeverSpec(wc_budget_global={"32684": 1.50}, label="+50% assy (WC32684)")),
    "radassy_50": ("+50% radome assembly (AEROA)", lambda: LeverSpec(wc_budget_global={"AEROA": 1.50}, label="+50% radome assy (AEROA)")),
    "radpaint_50": ("+50% radome paint (WC236)", lambda: LeverSpec(wc_budget_global={"236": 1.50}, label="+50% radome paint (WC236)")),
}


def _units_by_prog(ds: DataSource):
    return {p: [u.as_sim_unit() for u in ds.get_wip_units(p) if not u.stalled]
            for p in PSVC.program_order()}


def get_bottlenecks(ds: DataSource):
    return bottleneck_load(_units_by_prog(ds), ds.as_of())


def run_preset(ds: DataSource, preset_key: str):
    if preset_key not in PRESETS:
        return None
    _label, factory = PRESETS[preset_key]
    return run_lever(_units_by_prog(ds), ds.as_of(), factory())


def back_solve_program(ds: DataSource, program: str):
    """Tactical: for each late unit, what capacity on the binding WC would hold contract?
    DATA-GATED: only runs when the program's model is TRAINED (else returns gated notice)."""
    ubp = _units_by_prog(ds)
    binding = BINDING_WC[program]
    results = []
    gated = True
    for u in ds.get_wip_units(program):
        if u.stalled or not u.commit:
            continue
        feats = _fb.build(u.serial, u.so, program, u.maxop).model_features()
        pred = registry_model.predict(program, feats)
        if pred.mode != "TRAINED":
            gated = True
            continue
        gated = False
        r = back_solve(ubp, ds.as_of(), u.serial, program, u.commit,
                       pred.p50_days, binding)
        if not r.achievable or (r.needed_mult and r.needed_mult > 1.0):
            results.append(r)
    return dict(program=program, binding_wc=binding, gated=gated, results=results)
