"""Validate LLM-extracted WI constraints against the hand-mined router_registry cures.

This is the GATE: WI extraction must never silently diverge from the running sim.
Matching is tolerant — cure dwell hours within a relative tolerance, matched by nearest
op and/or dwell magnitude, because the LLM labels won't be byte-identical to ours.
"""
from dataclasses import dataclass, field
from app.engines.router_registry import registry


# Router cures whose dwell comes from IFS MACH_RUN (oven/autoclave programs), NOT WI
# text — the LLM cannot extract these (no stated hour duration in the WI). Excluded from
# the WI-extractable match rate; they stay sourced from IFS.
IFS_SOURCED_NOTE = "MACH_RUN"  # note substring marking an IFS-sourced (non-WI) cure


def _is_ifs_sourced(note: str) -> bool:
    return note is not None and IFS_SOURCED_NOTE in note


@dataclass
class ValidationReport:
    program: str
    matched: list = field(default_factory=list)      # (router_cure, extracted_cure)
    missing: list = field(default_factory=list)      # WI-extractable router cures NOT found
    ifs_sourced: list = field(default_factory=list)  # router cures sourced from IFS (excluded)
    extra: list = field(default_factory=list)        # LLM cures with no router match (candidates)
    n_router: int = 0
    n_extracted: int = 0

    @property
    def n_wi_extractable(self):
        return len(self.matched) + len(self.missing)

    @property
    def match_rate(self):
        d = self.n_wi_extractable
        return (len(self.matched) / d) if d else 0.0

    def summary(self) -> str:
        return (f"{self.program}: matched {len(self.matched)}/{self.n_wi_extractable} "
                f"WI-extractable router cures ({self.match_rate*100:.0f}%); "
                f"{len(self.ifs_sourced)} IFS-sourced (oven, excluded); "
                f"{len(self.missing)} missing; {len(self.extra)} new candidates")


def _hours_close(a, b, rel=0.20, absol=1.0):
    """Match cure hours within 20% or 1hr, whichever is larger — tight enough that a
    30-min air-dry never matches a 2hr cure, loose enough for RT/oven path differences."""
    if a is None or b is None:
        return False
    return abs(a - b) <= max(absol, rel * max(a, b))


def validate(program: str, extracted_cures: list) -> ValidationReport:
    """extracted_cures: list[CureSpec]. Router cures tuple: (after_op, label, dwell_hr, note).
    IFS-sourced (oven MACH_RUN) cures are set aside — the LLM can't extract them and they
    stay sourced from IFS. Match rate is measured only over WI-extractable cures."""
    router_cures = registry.cures(program)
    rep = ValidationReport(program=program, n_router=len(router_cures),
                           n_extracted=len(extracted_cures))
    used = set()
    for (rop, rlabel, rhr, rnote) in router_cures:
        if _is_ifs_sourced(rnote):
            rep.ifs_sourced.append((rop, rlabel, rhr, rnote))
            continue
        best = None
        for i, ec in enumerate(extracted_cures):
            if i in used:
                continue
            eh = ec.dwell_hours()
            op_ok = (ec.op is None) or (rop is None) or (ec.op == rop) or (abs((ec.op or 0) - rop) <= 15)
            if _hours_close(rhr, eh) and op_ok:
                best = i
                break
        if best is not None:
            used.add(best)
            rep.matched.append(((rop, rlabel, rhr), extracted_cures[best]))
        else:
            rep.missing.append((rop, rlabel, rhr, rnote))
    for i, ec in enumerate(extracted_cures):
        if i not in used and ec.dwell_hours() is not None:
            rep.extra.append(ec)
    return rep
