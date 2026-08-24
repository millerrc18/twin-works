"""Regression tests — the safety net for engine/registry refactors.

The golden-master test asserts forecast output (sim/P50/P80/Δ per unit, all programs) has not
drifted. Capture the reference once with `python -m tests.golden capture`, then this fails on any
change. Re-capture deliberately only when a forecast change is INTENDED.
"""
import os
os.environ.setdefault("RTG_DATA_SOURCE", "snapshot")

from tests import golden


def test_forecast_matches_golden_master():
    ok, diffs = golden.check()
    if not ok:
        lines = [f"{p} SO {so}: golden={a} now={b}" for p, so, a, b in diffs[:20]]
        raise AssertionError("Forecast drifted from golden master:\n" + "\n".join(lines))


def test_db_and_routers_sources_agree():
    """DB-source and routers-source program configs must produce identical forecasts."""
    from app.config import settings
    from app.services import program_service as PSVC
    from app.engines import router_registry as RR
    from app.services import position_state as PS
    from app.data.snapshot_source import SnapshotDataSource
    from app.services import forecast_service as FS

    def snap():
        PS.invalidate_cache(); PSVC.invalidate_cache(); RR.rebuild()
        ds = SnapshotDataSource()
        out = {}
        for p in PSVC.program_order() or ["ELEV", "RAD", "AEGIS"]:
            out[p] = [(f.serial, str(f.p50), str(f.p80)) for f in FS.forecast_program(ds, p)]
        return out

    orig = settings.program_source
    try:
        settings.program_source = "db"
        db_out = snap()
        settings.program_source = "routers"
        routers_out = snap()
    finally:
        settings.program_source = orig
        PSVC.invalidate_cache(); RR.rebuild()

    # both sources define the same 3 seed programs -> identical forecasts
    for p in ("ELEV", "RAD", "AEGIS"):
        assert db_out.get(p) == routers_out.get(p), f"{p} differs between db and routers source"
