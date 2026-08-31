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


def test_golden_snapshot_uses_bootstrap_data_not_mutable_position_state(monkeypatch):
    """The golden fixture must not change when a live sync updates PositionState."""
    from app.data import wip_tables as W
    from app.services import position_state as PS

    monkeypatch.setattr(PS, "load_state", lambda: {
        "1452748": {
            "program": "ELEV", "serial": "LH 229", "maxop": 4200,
            "last_clock": W.AS_OF.date(), "due": W.d(9, 4),
            "closed": None, "pack": None,
        },
    })

    snapshot = golden._forecast_snapshot()
    unit = next(row for row in snapshot["ELEV"] if row["so"] == "1452748")

    assert unit["maxop"] == W.STATUS_MAXCLOSED["1452748"]


def test_golden_snapshot_checks_only_seed_programs(monkeypatch):
    """A fourth configured program must not invalidate the seed golden master."""
    from app.services import program_service as PSVC

    monkeypatch.setattr(PSVC, "program_order", lambda: ["ELEV", "RAD", "AEGIS", "TEST4"])

    snapshot = golden._forecast_snapshot()

    assert list(snapshot) == ["ELEV", "RAD", "AEGIS"]


def test_db_and_routers_sources_agree():
    """DB-source and routers-source program configs must produce identical forecasts."""
    from app.config import settings
    from app.services import program_service as PSVC
    from app.engines import router_registry as RR
    from app.services import position_state as PS
    from app.data.snapshot_source import SnapshotDataSource
    from app.services import forecast_service as FS

    def snap():
        PS.invalidate_cache()
        PSVC.invalidate_cache()
        RR.rebuild()
        ds = SnapshotDataSource()
        out = {}
        seed_programs = ("ELEV", "RAD", "AEGIS")
        for p in seed_programs:
            out[p] = [(f.serial, str(f.p50_date), str(f.p80_date))
                      for f in FS.forecast_program(ds, p, programs=seed_programs)]
        return out

    orig = settings.program_source
    try:
        settings.program_source = "db"
        db_out = snap()
        settings.program_source = "routers"
        routers_out = snap()
    finally:
        settings.program_source = orig
        PSVC.invalidate_cache()
        RR.rebuild()

    # both sources define the same 3 seed programs -> identical forecasts
    for p in ("ELEV", "RAD", "AEGIS"):
        assert db_out.get(p) == routers_out.get(p), f"{p} differs between db and routers source"
