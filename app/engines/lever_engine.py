"""Lever engine — counterfactual "what-if" driver over the finite-capacity sim.

The flagship decision feature: re-run the sim with modified capacity/crew/priority and
diff the finishes to show WHERE acting changes throughput. Pure function of the sim; no
ML, no DB. Two views:
  - per-unit deltas (which units move, by how many days)
  - systemic bottleneck load (which WC binds; what +capacity buys fleet-wide)

Levers are applied by temporarily patching the routers module globals that crew() and
wc_shift_budget() read, running the sim, then restoring — no permanent global mutation.
"""
import copy
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import routers as R
from app.engines.rtg_wrapper import run_pooled


@dataclass
class LeverSpec:
    """A what-if scenario. All fields optional; unset = baseline."""
    wc_budget_mult: dict = field(default_factory=dict)   # {(program,wc): multiplier}
    wc_budget_global: dict = field(default_factory=dict)  # {wc: multiplier} across programs
    crew_override: dict = field(default_factory=dict)     # {opno: crew_factor}
    label: str = "scenario"


@contextmanager
def _apply(spec: LeverSpec):
    orig_wc = copy.deepcopy(R.WC_SHIFT)
    orig_crew = copy.deepcopy(R.CREW_BY_OP)
    try:
        # per-(program,wc) multipliers
        for (prog, wc), mult in spec.wc_budget_mult.items():
            key = (prog, wc)
            base = R.WC_SHIFT.get(key)
            if base:
                R.WC_SHIFT[key] = {s: h * mult for s, h in base.items()}
        # global-per-wc multipliers (all programs that use that wc)
        for wc, mult in spec.wc_budget_global.items():
            for key in list(R.WC_SHIFT.keys()):
                if key[1] == wc:
                    R.WC_SHIFT[key] = {s: h * mult for s, h in R.WC_SHIFT[key].items()}
        # crew overrides
        for opno, cf in spec.crew_override.items():
            R.CREW_BY_OP[opno] = cf
        yield
    finally:
        R.WC_SHIFT.clear()
        R.WC_SHIFT.update(orig_wc)
        R.CREW_BY_OP.clear()
        R.CREW_BY_OP.update(orig_crew)


@dataclass
class UnitDelta:
    serial: str
    program: str
    baseline_finish: object
    scenario_finish: object
    delta_days: int


@dataclass
class LeverResult:
    label: str
    unit_deltas: list          # list[UnitDelta]
    total_days_pulled_in: int  # sum of improvements (negative deltas)
    units_improved: int
    max_pull_in: int


def _sim_all(units_by_prog, as_of):
    """Run the pooled sim for all programs. Accepts the {code: [units]} dict directly."""
    return run_pooled(units_by_prog, as_of)


def run_lever(units_by_prog: dict, as_of: datetime, spec: LeverSpec) -> LeverResult:
    """units_by_prog: {'ELEV':[sim_unit...], 'RAD':[...], 'AEGIS':[...]}. Returns deltas
    of scenario vs baseline finishes (negative delta = pulled EARLIER = good)."""
    baseline = _sim_all(units_by_prog, as_of)
    with _apply(spec):
        scenario = _sim_all(units_by_prog, as_of)

    prog_of = {}
    for p, us in units_by_prog.items():
        for u in us:
            prog_of[u["serial"]] = p

    deltas = []
    for serial, b in baseline.items():
        s = scenario.get(serial)
        if not (b.get("finish") and s and s.get("finish")):
            continue
        bf, sf = b["finish"].date(), s["finish"].date()
        d = (sf - bf).days
        deltas.append(UnitDelta(serial, prog_of.get(serial, "?"), bf, sf, d))
    deltas.sort(key=lambda x: x.delta_days)   # biggest pull-in first
    improved = [x for x in deltas if x.delta_days < 0]
    return LeverResult(
        label=spec.label, unit_deltas=deltas,
        total_days_pulled_in=-sum(x.delta_days for x in improved),
        units_improved=len(improved),
        max_pull_in=(-improved[0].delta_days if improved else 0))


@dataclass
class BackSolveResult:
    serial: str
    program: str
    contract: object
    baseline_p50: object
    achievable: bool
    needed_wc: str | None
    needed_mult: float | None   # capacity multiplier on the binding WC to hit contract
    residual_days: float


def back_solve(units_by_prog: dict, as_of: datetime, serial: str, program: str,
               contract: date, residual_days: float, binding_wc: str) -> BackSolveResult:
    """Tactical: 'what must be true for the contract date to hold?' Binary-search a capacity
    multiplier on the binding WC until sim(serial)+residual <= contract. residual_days comes
    from the ML/empirical model so the answer reflects realistic (not happy-path) dates.
    DATA-GATED: only meaningful once the ML model is TRAINED (caller enforces)."""
    def finish_with(mult):
        spec = LeverSpec(wc_budget_global={binding_wc: mult}, label="backsolve")
        with _apply(spec):
            sim = _sim_all(units_by_prog, as_of)
        r = sim.get(serial)
        if not (r and r.get("finish")):
            return None
        return r["finish"].date() + timedelta(days=round(residual_days))

    base = finish_with(1.0)
    if base is None:
        return BackSolveResult(serial, program, contract, None, False, None, None, residual_days)
    if base <= contract:
        return BackSolveResult(serial, program, contract, base, True, None, 1.0, residual_days)
    # search up to 3x capacity
    lo, hi = 1.0, 3.0
    if finish_with(hi) is None or finish_with(hi) > contract:
        return BackSolveResult(serial, program, contract, base, False, binding_wc, None, residual_days)
    for _ in range(12):
        mid = (lo + hi) / 2
        f = finish_with(mid)
        if f and f <= contract:
            hi = mid
        else:
            lo = mid
    return BackSolveResult(serial, program, contract, base, True, binding_wc, round(hi, 2), residual_days)


def bottleneck_load(units_by_prog: dict, as_of: datetime) -> list:
    """Systemic view: for each shared/bottleneck WC, weekly demand (from the baseline op
    schedule) vs available budget. Flags weeks over 100%. Returns per-WC summary rows."""
    from app.engines import rtg_wrapper as wrapper
    from app.services.capacity_metrics import work_center_load_rows

    focus = sorted(wrapper.shared_wcs() | {"236", "32684", "AEROL", "AEROA"})
    metrics = work_center_load_rows(units_by_prog, as_of, work_centers=set(focus))
    rows = []
    for wc in focus:
        item = metrics[wc]
        capacity = item["modeled_weekly_capacity_hours"]
        rows.append(dict(
            wc=wc,
            avail_per_wk=round(capacity) if capacity is not None else 0,
            peak_demand=round(item["peak_weekly_demand_hours"]),
            weeks_over=item["weeks_over_capacity"],
            shared=(wc in wrapper.shared_wcs()),
            util_pct=item["peak_weekly_utilization_pct"],
        ))
    rows.sort(key=lambda r: (r["util_pct"] or 0), reverse=True)
    return rows
