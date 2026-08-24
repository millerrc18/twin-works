"""DatasetBuilder — formalizes the backtest reconstruction into DB-backed training rows.

Parameterized reconstruction helpers (TL + SO_META passed in, not module globals) so this
is importable and testable. One ml_training_row per closed unit: features at its logged
snapshot + residual target (actual_close - sim_forecast).
"""
import json
from datetime import datetime as DT, date, timedelta
from pathlib import Path
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MLTrainingRow
from app.data import wip_tables as W
from app.engines.rtg_wrapper import run_pooled
from app.engines.router_registry import registry
from ml.model.features import FeatureBuilder

BASE = Path(__file__).resolve().parent.parent.parent
TIMELINE_JSON = BASE / "backtest_timeline.json"


def _pdate(s):
    return DT.strptime(s, "%Y-%m-%d").date() if s else None


def maxop_at(tl: dict, so: str, S: date, floor: int):
    """Highest op last-clocked on/before S (mirrors live MAX_CLOSED). Param TL."""
    ops = tl.get(so, {})
    done = [int(o) for o, cl in ops.items() if _pdate(cl) <= S and int(o) >= floor]
    return max(done) if done else None


def concurrent_pool(tl: dict, so_meta: dict, prog_group: tuple, S: date):
    """In-process SOs at S across a program group (has clock, not shipped, below ship op)."""
    pool = []
    for so, m in so_meta.items():
        if m["program"] not in prog_group:
            continue
        if m.get("close") and m["close"] <= S:
            continue
        spec = registry.spec(m["program"])
        mo = maxop_at(tl, so, S, spec.floor_op)
        if mo is None or mo >= spec.ship_op:
            continue
        pool.append(dict(serial=so, so=so, maxop=mo, commit=None, program=m["program"]))
    return pool


def _so_meta_from_shipped():
    """Build SO_META {so: {program, close}} from the SHIPPED tables."""
    meta = {}
    for prog in ("ELEV", "RAD", "AEGIS"):
        for (serial, so, commit, close, pack, fx) in W.SHIPPED.get(prog, []):
            meta[so] = dict(program=prog, close=close, serial=serial, pack=pack)
    return meta


def build_training_rows() -> list[dict]:
    """For each of the 8 shipped units, reconstruct pooled position ~14d before close,
    run the sim from that snapshot, and emit (features, residual) rows. Returns dicts."""
    tl = json.load(open(TIMELINE_JSON))
    so_meta = _so_meta_from_shipped()
    fb = FeatureBuilder()
    POOL = {"ELEV": ("ELEV", "AEGIS"), "AEGIS": ("ELEV", "AEGIS"), "RAD": ("RAD",)}
    rows = []
    for so, m in so_meta.items():
        prog = m["program"]
        close = m["close"]
        pack = m.get("pack") or close
        S = close - timedelta(days=14)   # snapshot horizon used for the training feature
        spec = registry.spec(prog)
        maxop_S = maxop_at(tl, so, S, spec.floor_op)
        if maxop_S is None:
            continue
        # pooled sim from snapshot S
        pool = concurrent_pool(tl, so_meta, POOL[prog], S)
        if not any(u["so"] == so for u in pool):
            pool.append(dict(serial=so, so=so, maxop=maxop_S, commit=None, program=prog))
        as_of = DT.combine(S, DT.min.time()).replace(hour=6)
        units_by_program = {}
        for u in pool:
            units_by_program.setdefault(u["program"], []).append(u)
        sim = run_pooled(units_by_program, as_of)
        r = sim.get(so)
        sim_fin = r["finish"].date() if r and r.get("finish") else None
        if sim_fin is None:
            continue
        residual = (pack - sim_fin).days      # actual(pack) - sim ; +ve = sim optimistic
        fv = fb.build(m["serial"], so, prog, maxop_S)
        row = fv.to_row()
        row.update(dict(sim_forecast_date=sim_fin, actual_close_date=pack,
                        residual_days=float(residual), milestone_phase=fv.milestone_phase))
        rows.append(row)
    return rows


async def persist_training_rows(db: AsyncSession) -> dict:
    rows = build_training_rows()
    await db.execute(delete(MLTrainingRow))  # rebuild (idempotent)
    for r in rows:
        db.add(MLTrainingRow(
            serial=r["serial"], so=r["so"], program=r["program"],
            milestone_phase=r["milestone_phase"], crew_at_op=r["crew_at_op"],
            raw_dwell_days=r["raw_dwell_days"], cleaned_dwell_days=r["cleaned_dwell_days"],
            wi_complexity_score=r["wi_complexity_score"], sharedwc_queue=None,
            sim_forecast_date=r["sim_forecast_date"], actual_close_date=r["actual_close_date"],
            residual_days=r["residual_days"]))
    await db.commit()
    return dict(n_rows=len(rows), rows=rows)
