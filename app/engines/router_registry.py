"""ProgramRegistry — the one shim that makes routers.py constants data-addressable.

routers.py stays untouched (it's the source of truth). This wraps its module-level
constants into a per-program object the sim wrapper, WI validator, lever engine, and
feature builder all reference by program code ('ELEV'|'RAD'|'AEGIS').
"""
from dataclasses import dataclass, field

import routers as R

# milestone op-ceilings (from routers.py header comment — authoritative boundaries)
MILESTONE_CEILINGS = {
    "ELEV": [("AJ", 1300), ("A1", 2800), ("A2", 3600), ("FS", 4200)],
    "RAD":  [("LAM", 570), ("ASSY", 710), ("PAINT", 755), ("SHIP", 790)],
    "AEGIS": [("LAM", 195), ("ASSY", 245), ("PAINT", 370), ("SHIP", 400)],
}

# pack/ship op per program (physical-ship signal; highest real op)
PACK_OP = {"ELEV": 4200, "RAD": 790, "AEGIS": 380}
SHIP_OP = {"ELEV": 4200, "RAD": 790, "AEGIS": 400}
FLOOR_OP = {"ELEV": 0, "RAD": 0, "AEGIS": 90}  # ignore stray sub-floor ops


@dataclass(frozen=True)
class ProgramSpec:
    code: str
    ops: list          # (opno, desc, wc, hr, ms)
    cures: list        # (after_op, label, dwell_hr, note)
    milestones: list   # (code, name)
    ceilings: list     # (ms_code, max_op)
    pack_op: int
    ship_op: int
    floor_op: int
    crew_by_op: dict = field(default_factory=dict)
    dpas: bool = False

    def cure_floor_hours(self, maxop=None) -> float:
        """Sum of cure dwell still ahead of maxop (full floor if not started)."""
        if maxop is None:
            return sum(c[2] for c in self.cures)
        return sum(c[2] for c in self.cures if c[0] > maxop)

    def milestone_of(self, maxop) -> str:
        if maxop is None:
            return self.ceilings[0][0]
        for code, ceil in self.ceilings:
            if maxop <= ceil:
                return code
        return self.ceilings[-1][0]


@dataclass
class ProgramRegistry:
    programs: dict = field(default_factory=dict)

    def spec(self, code: str) -> ProgramSpec:
        return self.programs[code]

    # data-addressable accessors used across the app
    def ops(self, code): return self.programs[code].ops
    def cures(self, code): return self.programs[code].cures
    def milestones(self, code): return self.programs[code].milestones

    def ops_map(self) -> dict:
        return {c: p.ops for c, p in self.programs.items()}

    def cures_map(self) -> dict:
        return {c: p.cures for c, p in self.programs.items()}

    # pass-throughs to routers helpers (single source of truth)
    @staticmethod
    def crew(wc, opno=None): return R.crew(wc, opno)

    @staticmethod
    def wc_shift_budget(program, wc, shift): return R.wc_shift_budget(program, wc, shift)

    @staticmethod
    def elevator_weekend_factor(dd): return R.elevator_weekend_factor(dd)

    @property
    def dpas_programs(self): return R.DPAS_PROGRAMS

    @property
    def shared_wc(self): return R.SHARED_WC


def _tuple_ops(ops):
    """JSON round-trips ops as lists; the sim/engine expect tuples. Normalize."""
    return [tuple(o) for o in ops]


def _routers_registry() -> "ProgramRegistry":
    """The original hardcoded build — the fallback + the seed source of truth."""
    reg = ProgramRegistry()
    reg.programs["ELEV"] = ProgramSpec(
        "ELEV", R.ELEVATOR_OPS, R.ELEVATOR_CURES, R.ELEV_MILESTONES,
        MILESTONE_CEILINGS["ELEV"], PACK_OP["ELEV"], SHIP_OP["ELEV"], FLOOR_OP["ELEV"],
        crew_by_op=dict(R.CREW_BY_OP), dpas="ELEV" in R.DPAS_PROGRAMS)
    reg.programs["RAD"] = ProgramSpec(
        "RAD", R.RADOME_OPS, R.RADOME_CURES, R.RAD_MILESTONES,
        MILESTONE_CEILINGS["RAD"], PACK_OP["RAD"], SHIP_OP["RAD"], FLOOR_OP["RAD"],
        crew_by_op=dict(R.CREW_BY_OP), dpas="RAD" in R.DPAS_PROGRAMS)
    reg.programs["AEGIS"] = ProgramSpec(
        "AEGIS", R.AEGIS_OPS, R.AEGIS_CURES, R.AEGIS_MILESTONES,
        MILESTONE_CEILINGS["AEGIS"], PACK_OP["AEGIS"], SHIP_OP["AEGIS"], FLOOR_OP["AEGIS"],
        crew_by_op=dict(R.CREW_BY_OP), dpas="AEGIS" in R.DPAS_PROGRAMS)
    return reg


def build_registry() -> "ProgramRegistry":
    """Prefer DB-defined programs (program table via program_service); fall back to routers.py
    when the table is empty or RTG_PROGRAM_SOURCE=routers. DB specs are normalized to tuples so
    the sim output is byte-identical to the hardcoded path."""
    try:
        from app.services.program_service import load_specs
        specs = load_specs()
    except Exception:
        specs = {}
    if not specs:
        return _routers_registry()
    reg = ProgramRegistry()
    for code, s in specs.items():
        reg.programs[code] = ProgramSpec(
            code, _tuple_ops(s["ops"]), _tuple_ops(s["cures"]),
            [tuple(m) for m in s["milestones"]], [tuple(c) for c in s["ceilings"]],
            s["pack_op"], s["ship_op"], s["floor_op"],
            crew_by_op=dict(s["crew_by_op"]), dpas=bool(s["dpas"]))
    return reg


def rebuild():
    """Refresh the existing registry so already-imported consumers see program changes."""
    fresh = build_registry()
    registry.programs = fresh.programs
    return registry


# module-level singleton
registry = build_registry()
