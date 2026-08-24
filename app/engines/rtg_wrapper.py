"""Thin adapter over capacity_engine.simulate — the one place the app calls the sim.

Handles the elevator+Aegis shared-capacity pooling (they share paint booth WC221 +
ovens 32678), matching build_tracker's pooled-sim behavior. Radome runs separately.
"""
from datetime import datetime
from capacity_engine import simulate
from app.engines.router_registry import registry


def run_sim(units, as_of: datetime, ops_map=None, cures_map=None) -> dict:
    """units: list of {serial, so, maxop, commit, program}. Returns
    {serial: {finish, op_dt, cure_dt}} straight from simulate()."""
    ops_map = ops_map or registry.ops_map()
    cures_map = cures_map or registry.cures_map()
    return simulate(units, ops_map, cures_map, as_of)


def run_pooled(elev_units, aegis_units, radome_units, as_of: datetime) -> dict:
    """Run the sim the way build_tracker does: elevator+Aegis pooled (shared WC221/32678,
    DPAS priority handled inside simulate), radome separate. Returns a single merged
    {serial: result} dict across all programs."""
    pooled_in = list(elev_units) + list(aegis_units)
    pooled = run_sim(pooled_in, as_of) if pooled_in else {}
    rad = run_sim(radome_units, as_of) if radome_units else {}
    merged = dict(pooled)
    merged.update(rad)
    return merged
