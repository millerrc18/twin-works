"""Golden-master regression harness for the forecast engine.

Captures a deterministic snapshot of forecast output for every program (sim/P50/P80/Δ per unit)
so refactors can be proven not to move a single date. Run in SNAPSHOT data mode against a fixed
program config + PositionState so results are reproducible.

  python -m tests.golden capture   # write tests/golden_forecast.json (the reference)
  python -m tests.golden check     # regenerate + diff vs the reference (exit 1 on drift)

The pytest test (test_regression.py) calls check() and asserts no drift.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden_forecast.json"


def _forecast_snapshot() -> dict:
    """Deterministic forecast output for all programs. Forces snapshot mode + baseline positions
    (empty PositionState -> wip_tables baseline) so the golden master is stable across runs."""
    # ensure snapshot mode + a fixed as-of by using the wip_tables baseline (PositionState empty)
    from app.services import position_state as PS
    from app.services import program_service as PSVC
    from app.engines import router_registry as RR
    from app.data.snapshot_source import SnapshotDataSource
    from app.services import forecast_service as FS

    PS.invalidate_cache()
    PSVC.invalidate_cache()
    RR.rebuild()
    ds = SnapshotDataSource()

    order = PSVC.program_order() or ["ELEV", "RAD", "AEGIS"]
    out = {}
    for p in order:
        rows = []
        for f in FS.forecast_program(ds, p):
            rows.append(dict(
                serial=f.serial, so=f.so, maxop=f.maxop,
                sim=f.sim_finish.isoformat() if f.sim_finish else None,
                p50=f.p50.isoformat() if f.p50 else None,
                p80=f.p80.isoformat() if f.p80 else None,
                delta=f.delta_contract, stalled=f.stalled))
        rows.sort(key=lambda r: (r["so"] or ""))
        out[p] = rows
    return out


def capture() -> dict:
    snap = _forecast_snapshot()
    GOLDEN.write_text(json.dumps(snap, indent=2, sort_keys=True))
    n = sum(len(v) for v in snap.values())
    print(f"captured golden master: {len(snap)} programs, {n} units -> {GOLDEN.name}")
    return snap


def check() -> tuple[bool, list]:
    """Return (ok, diffs). ok=True means current output matches the golden master exactly."""
    if not GOLDEN.exists():
        raise FileNotFoundError("no golden master — run `python -m tests.golden capture` first")
    ref = json.loads(GOLDEN.read_text())
    cur = _forecast_snapshot()
    diffs = []
    for prog in sorted(set(ref) | set(cur)):
        rref = {r["so"]: r for r in ref.get(prog, [])}
        rcur = {r["so"]: r for r in cur.get(prog, [])}
        for so in sorted(set(rref) | set(rcur)):
            a, b = rref.get(so), rcur.get(so)
            if a != b:
                diffs.append((prog, so, a, b))
    return (not diffs), diffs


if __name__ == "__main__":
    # snapshot mode for reproducibility
    os.environ.setdefault("RTG_DATA_SOURCE", "snapshot")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "capture":
        capture()
    else:
        ok, diffs = check()
        if ok:
            print("PASS — forecast output matches golden master (no drift)")
        else:
            print(f"FAIL — {len(diffs)} unit(s) drifted from golden master:")
            for prog, so, a, b in diffs[:20]:
                print(f"  {prog} SO {so}:\n    golden: {a}\n    now   : {b}")
            sys.exit(1)
