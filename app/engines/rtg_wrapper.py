"""Thin adapter over capacity_engine.simulate — the one place the app calls the sim.

Pooling is data-driven: programs that SHARE A WORK CENTER simulate TOGETHER (so the engine sees
their contention for that WC); programs that share nothing simulate separately. Pool membership =
connected components of the Program<->WorkCenter graph over shared WCs.

Two site facts (from the PM) make this correct and safe:
  1. WC names are GLOBALLY UNIQUE across all three plants — so a shared WC number always means the
     same physical resource; the graph can never wrongly merge programs that don't truly contend.
  2. Plant is a real boundary (ELEV+AEGIS=Plant 2, RAD=Plant 3). We ALSO require same-plant as a
     belt-and-suspenders guard, so a mis-entered WC number can never silently pool across plants.

Today this reproduces the original hardcoded rule exactly — ELEV+AEGIS share paint WC221 + WC32687
in Plant 2 (pool), RAD shares nothing and is Plant 3 (separate) — but a NEW program auto-pools iff
it's in the same plant AND its routing touches a shared WC. No pool_group label to get wrong.
"""
from datetime import datetime
from capacity_engine import simulate
from app.engines.router_registry import registry
from app.services import program_service as PSVC


def run_sim(units, as_of: datetime, ops_map=None, cures_map=None) -> dict:
    """units: list of {serial, so, maxop, commit, program}. Returns
    {serial: {finish, op_dt, cure_dt}} straight from simulate()."""
    ops_map = ops_map or registry.ops_map()
    cures_map = cures_map or registry.cures_map()
    return simulate(units, ops_map, cures_map, as_of)


def _program_wcs(code: str) -> set:
    """The set of work centers a program's routing touches (from its ops)."""
    try:
        return {op[2] for op in registry.spec(code).ops if len(op) > 2 and op[2]}
    except Exception:
        return set()


def _plants(codes) -> dict:
    """{code: plant}. Empty-string plant for the seed programs (routers fallback has no plant);
    when all plants are '', the plant guard is a no-op and pooling falls back to shared-WC only —
    which is still correct because WCs are globally unique."""
    specs = PSVC.load_specs()
    return {c: (specs.get(c, {}).get("plant", "") if specs else "") for c in codes}


def shared_wcs() -> set:
    """Work centers that appear in >=2 active programs' routings = the contended resources.
    Derived (not a hardcoded set) so a new program's shared WCs are picked up automatically."""
    from collections import Counter
    seen = Counter()
    for code in registry.programs:
        for wc in _program_wcs(code):
            seen[wc] += 1
    return {wc for wc, n in seen.items() if n >= 2}


def pool_groups(codes) -> list:
    """Partition program codes into pools: two programs are in the same pool iff they share at
    least one shared WC (transitive). Returns a list of code-lists (connected components)."""
    codes = list(codes)
    shared = shared_wcs()
    # program -> its shared WCs
    pwc = {c: (_program_wcs(c) & shared) for c in codes}
    parent = {c: c for c in codes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    # union any two programs that share a WC AND are in the same plant (plant = hard guard;
    # WCs are globally unique so a shared WC already implies same physical resource, but the
    # plant check makes a mis-entered WC number unable to pool across plants).
    plant = _plants(codes)
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            if (pwc[a] & pwc[b]) and plant.get(a) == plant.get(b):
                union(a, b)
    groups = {}
    for c in codes:
        groups.setdefault(find(c), []).append(c)
    # deterministic order (by first code in each group, and codes sorted within)
    return [sorted(g) for _, g in sorted(groups.items())]


def run_pooled(units_by_program: dict, as_of: datetime) -> dict:
    """units_by_program: {code: [unit dicts]}. Simulate each shared-WC-connected pool together,
    merge results into one {serial: result} dict. Programs with no shared WC run alone."""
    merged = {}
    codes = [c for c in units_by_program if units_by_program.get(c)]
    for group in pool_groups(codes):
        pooled_in = []
        for c in group:
            pooled_in += list(units_by_program.get(c, []))
        if pooled_in:
            merged.update(run_sim(pooled_in, as_of))
    return merged
