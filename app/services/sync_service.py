"""Sync service — the one place the refresh loop lives.

Button 1  sync_positions : pull current op position + last-clock + due for every live WIP unit
                           from IFS, upsert PositionState, stamp today's ForecastLog build.
Button 2  process_ships   : (fast) detect newly-closed SOs, mark them shipped + backfill their
                           ForecastLog accuracy; (slow) re-score forward accuracy, rebuild
                           training rows, retrain if a program hit its threshold, reload registry.

IFS reads use the existing audited SQL in live_source and run in a thread (blocking urllib) so
the async event loop isn't stalled. DB writes are per-program transactions; IFS calls never sit
inside a DB transaction. A SyncRun row acts as a single-run lock.
"""
import asyncio
import json
from datetime import datetime, date
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SyncRun, PositionState
from app.data import token_store
from app.data.ifs_mcp_client import IfsMcpClient
from app.data.live_source import PROG_IFS, SQL_WIP, SQL_POSITION, SQL_LASTCLK
from app.data import wip_tables as W
from app.services import position_state as PS
from app.services import forecast_log_service as FL

PROGRAMS = ("ELEV", "RAD", "AEGIS")

# pack/ship op per program (physical ship = last-clock on this op)
PACK_OP = {"ELEV": 4200, "RAD": 790, "AEGIS": 380}

# Only process ships that shipped on/after this date — the RTG program window. Older ships are
# history (already covered by the retrospective backtest); pulling them all floods the forward set.
SHIP_SINCE = "2026-08-01"

# SHIPPED SOs for a program since SHIP_SINCE. "Shipped" = the pack op was clocked (PHYSICAL ship)
# OR the SO was administratively closed. Pack-op completion is the true ship signal — the shop
# order CLOSE_DATE often lags days behind the physical ship (e.g. S/N 0515 packed 8/21, SO still
# 'Started'). We join the pack-op clock so a packed-but-not-closed unit is still detected.
SQL_CLOSED = """
SELECT s.ORDER_NO AS SO,
       TO_CHAR(s.REVISED_DUE_DATE,'YYYY-MM-DD') AS DUE,
       TO_CHAR(s.CLOSE_DATE,'YYYY-MM-DD') AS CLOSED,
       TO_CHAR(p.PACK_CLK,'YYYY-MM-DD') AS PACK
FROM SHOP_ORD_CFV s
LEFT JOIN (
    SELECT c.ORDER_NO, MAX(c.FINISH_TIME) AS PACK_CLK
    FROM GD_SHOP_FLOOR_CLOCKING c
    WHERE c.OPERATION_NO = {packop} AND c.FINISH_TIME IS NOT NULL
    GROUP BY c.ORDER_NO
) p ON p.ORDER_NO = s.ORDER_NO
WHERE s.PROJECT_ID = '{project}' AND s.PART_NO IN ({parts})
  AND ( s.CLOSE_DATE >= TO_DATE('{since}','YYYY-MM-DD')
        OR p.PACK_CLK >= TO_DATE('{since}','YYYY-MM-DD') )
"""

# head serial lives in SHOP_ORD_CFV.NOTE_TEXT as 'S/N nnn' (verified — same pattern the radome
# takt-plan uses). PART_NO gives elevator hand: ...501=LH, ...502=RH.
SQL_SERIALNOTE = """
SELECT s.ORDER_NO AS SO, s.PART_NO AS PART_NO, s.NOTE_TEXT AS NOTE_TEXT
FROM SHOP_ORD_CFV s
WHERE s.ORDER_NO IN ({sos})
"""

# last-clock on the pack op (physical ship date) for given SOs
SQL_PACKCLK = """
SELECT c.ORDER_NO AS SO, TO_CHAR(MAX(c.FINISH_TIME),'YYYY-MM-DD') AS PACK_CLK
FROM GD_SHOP_FLOOR_CLOCKING c
WHERE c.ORDER_NO IN ({sos}) AND c.OPERATION_NO = {packop} AND c.FINISH_TIME IS NOT NULL
GROUP BY c.ORDER_NO
"""


class SyncBusy(Exception):
    pass


class NotConnected(Exception):
    pass


# ---------- lock ----------
async def _acquire(db: AsyncSession, kind: str) -> SyncRun:
    active = (await db.execute(select(SyncRun).where(SyncRun.active == True))).scalars().first()  # noqa: E712
    if active:
        raise SyncBusy(f"a {active.kind} sync is already running")
    run = SyncRun(kind=kind, active=True, stage="starting", started_at=datetime.utcnow())
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def _finish(db: AsyncSession, run_id: int, result: dict | None = None, error: str | None = None):
    await db.execute(update(SyncRun).where(SyncRun.id == run_id).values(
        active=False, stage="error" if error else "done",
        result_json=json.dumps(result) if result else None,
        error=error, finished_at=datetime.utcnow()))
    await db.commit()


async def current_run(db: AsyncSession) -> SyncRun | None:
    return (await db.execute(
        select(SyncRun).order_by(SyncRun.id.desc()).limit(1))).scalars().first()


# ---------- IFS client ----------
async def _client(db: AsyncSession) -> IfsMcpClient:
    tokens = await token_store.load_tokens(db, "ifs")
    if not tokens or not tokens.get("access_token"):
        raise NotConnected("Connect IFS first")
    return IfsMcpClient(**tokens)


def _pull_program(client: IfsMcpClient, program: str) -> dict:
    """Blocking IFS pull for one program: {so: dict(maxop,last_clock,due,serial)}. Thread-run."""
    proj, parts = PROG_IFS[program]
    parts_in = ",".join(f"'{p}'" for p in parts)

    def rows(res):
        return res.get("data", []) if isinstance(res, dict) else (res or [])

    wip = rows(client.execute_query(SQL_WIP.format(project=proj, parts=parts_in)))
    sos = [r["SO"] for r in wip]
    if not sos:
        return {}
    so_in = ",".join(f"'{s}'" for s in sos)
    pos = {r["SO"]: r["MAX_CLOSED"] for r in rows(client.execute_query(SQL_POSITION.format(sos=so_in)))}
    clk = {r["SO"]: r["LAST_CLK"] for r in rows(client.execute_query(SQL_LASTCLK.format(sos=so_in)))}
    serials = _serials_from_notes(client, program, so_in)
    out = {}
    for r in wip:
        so = r["SO"]
        out[so] = dict(
            maxop=pos.get(so),
            last_clock=clk.get(so),
            due=r.get("DUE"),
            closed=r.get("CLOSED"),
            serial=serials.get(so) or _serial_for(program, so))
    return out


import re as _re


def _serials_from_notes(client, program: str, so_in: str) -> dict:
    """Build {SO: serial} by parsing SHOP_ORD_CFV.NOTE_TEXT ('S/N nnn') + PART_NO (hand).
    Source of truth for head serials — IFS has no serial column, but the note carries it.
    Elevator -> 'LH nnn'/'RH nnn' (hand from PART_NO 501/502); radome/aegis -> the bare number."""
    def rows(res):
        return res.get("data", []) if isinstance(res, dict) else (res or [])
    try:
        recs = rows(client.execute_query(SQL_SERIALNOTE.format(sos=so_in)))
    except Exception:
        return {}
    out = {}
    for r in recs:
        note = (r.get("NOTE_TEXT") or "")
        m = _re.search(r"S/?N\s*([0-9]+)", note, _re.I)
        if not m:
            continue
        num = m.group(1).lstrip("0") or "0"      # 'S/N 0515' -> 515 (strip zero-pad)
        if program == "ELEV":
            pn = r.get("PART_NO") or ""
            hand = "LH" if "501" in pn else ("RH" if "502" in pn else "")
            out[r["SO"]] = (f"{hand} {num}").strip()
        else:
            out[r["SO"]] = num
    return out


def _serial_for(program: str, so: str) -> str:
    tbl = {"ELEV": W.ELEV, "RAD": W.RAD, "AEGIS": W.AEGIS}[program]
    for row in tbl:
        if row[1] == so:
            return row[0]
    return so  # unknown SO -> label by SO (flagged "needs serial" in UI); never guessed


def _pd(s):
    return date.fromisoformat(s) if s else None


# ---------- Button 1: refresh positions ----------
async def sync_positions(db: AsyncSession) -> dict:
    client = await _client(db)                       # raises NotConnected
    run = await _acquire(db, "positions")            # raises SyncBusy
    try:
        # ensure PositionState is materialized before we start upserting onto it
        await PS.seed_from_baseline(db)              # no-op if already seeded

        moved, new_stall, unknown = [], [], []
        for program in PROGRAMS:
            pulled = await asyncio.to_thread(_pull_program, client, program)
            # snapshot prior maxops for the diff
            prior = {r.so: r.maxop for r in (await db.execute(
                select(PositionState).where(PositionState.program == program))).scalars().all()}
            for so, d in pulled.items():
                new_max = d["maxop"]
                if so in prior and prior[so] != new_max and new_max is not None:
                    moved.append(dict(so=so, serial=d["serial"], frm=prior[so], to=new_max))
                lc = _pd(d["last_clock"])
                if lc and (datetime.utcnow().date() - lc).days > 7:
                    new_stall.append(d["serial"])
                if d["serial"] == so:
                    unknown.append(so)
                await PS.upsert(db, so, program, d["serial"], maxop=new_max,
                                last_clock=lc, due=_pd(d["due"]), closed=_pd(d["closed"]),
                                source="ifs-sync")
            await db.commit()
        PS.invalidate_cache()

        # stamp today's forecast build (idempotent) off the freshly-synced snapshot source
        from app.data.snapshot_source import SnapshotDataSource
        ds = SnapshotDataSource()
        stamp = await FL.stamp_build(db, ds)

        result = dict(moved=moved, newly_stalled=sorted(set(new_stall)),
                      unknown_serials=unknown, forecast_build=stamp)
        await _finish(db, run.id, result=result)
        return result
    except Exception as e:
        await _finish(db, run.id, error=str(e)[:500])
        raise


# ---------- Button 2: process new ships ----------
def _pull_closed(client: IfsMcpClient, program: str) -> dict:
    """Blocking pull of SHIPPED SOs since SHIP_SINCE (pack-op clocked OR closed).
    {so: dict(closed, due, pack, ship, serial)}. `ship` = pack date if present else close date —
    the date used as the actual ship for accuracy scoring."""
    proj, parts = PROG_IFS[program]
    parts_in = ",".join(f"'{p}'" for p in parts)

    def rows(res):
        return res.get("data", []) if isinstance(res, dict) else (res or [])

    shipped = rows(client.execute_query(
        SQL_CLOSED.format(project=proj, parts=parts_in, since=SHIP_SINCE,
                          packop=PACK_OP[program])))
    sos = [r["SO"] for r in shipped]
    if not sos:
        return {}
    so_in = ",".join(f"'{s}'" for s in sos)
    serials = _serials_from_notes(client, program, so_in)
    out = {}
    for r in shipped:
        so = r["SO"]
        pack = r.get("PACK")
        closed = r.get("CLOSED")
        out[so] = dict(closed=closed, due=r.get("DUE"), pack=pack,
                       ship=(pack or closed),          # physical ship preferred
                       serial=serials.get(so) or _serial_for(program, so))
    return out


async def _already_closed_sos(db: AsyncSession) -> set:
    rows = (await db.execute(
        select(PositionState.so).where(PositionState.closed.isnot(None)))).scalars().all()
    return set(rows)


async def preview_ships(db: AsyncSession) -> dict:
    """Read-only: which SOs newly closed since last sync, and would any program cross threshold."""
    client = await _client(db)
    await PS.seed_from_baseline(db)
    known = await _already_closed_sos(db)
    from app.services import accuracy_forward as AF
    counts = AF.forward_counts()
    new_by_prog, would_train = {}, []
    for program in PROGRAMS:
        pulled = await asyncio.to_thread(_pull_closed, client, program)
        fresh = [dict(so=so, serial=d["serial"], closed=d["closed"])
                 for so, d in pulled.items() if so not in known]
        if fresh:
            new_by_prog[program] = fresh
    # threshold check
    from ml.model.registry import registry_model
    for program, fresh in new_by_prog.items():
        projected = counts.get(program, 0) + len(fresh)
        if projected >= registry_model.threshold_for(program):
            would_train.append(program)
    total = sum(len(v) for v in new_by_prog.values())
    return dict(new_count=total, new_by_program=new_by_prog, would_train=would_train)


async def process_ships_fast(db: AsyncSession) -> dict:
    """FAST stage (sync feedback): record newly-closed SOs + backfill their ForecastLog accuracy."""
    client = await _client(db)
    run = await _acquire(db, "ships")
    try:
        await PS.seed_from_baseline(db)
        known = await _already_closed_sos(db)
        recorded = []
        for program in PROGRAMS:
            pulled = await asyncio.to_thread(_pull_closed, client, program)
            for so, d in pulled.items():
                if so in known:
                    continue
                pack = _pd(d["pack"])
                ship = _pd(d["ship"])          # pack date preferred, else close date
                # Record the ship. `closed` in PositionState = the effective ship date so the
                # unit drops from WIP even when the SO close is still lagging (packed-not-closed).
                await PS.upsert(db, so, program, d["serial"], closed=ship, pack=pack,
                                due=_pd(d["due"]), source="ifs-sync")
                await db.commit()
                if ship:
                    await FL.backfill_close(db, d["serial"], ship)
                recorded.append(dict(so=so, serial=d["serial"],
                                     closed=d["closed"], pack=d["pack"], ship=d["ship"]))
        PS.invalidate_cache()
        # NOTE: run left ACTIVE on purpose; the slow stage finishes it.
        run_id = run.id
        return dict(run_id=run_id, recorded=recorded, n=len(recorded))
    except Exception as e:
        await _finish(db, run.id, error=str(e)[:500])
        raise


async def process_ships_slow(db: AsyncSession, run_id: int) -> dict:
    """SLOW stage (background): forward re-score, rebuild training rows, retrain, reload registry,
    append model-history. Idempotent; finishes the SyncRun row."""
    from ml.model.dataset import persist_training_rows
    from ml.model.trainer import train_all
    from ml.model.loader import refresh_registry
    from app.services import accuracy_forward as AF
    from app.services import model_history as MH
    try:
        await db.execute(update(SyncRun).where(SyncRun.id == run_id).values(stage="rescoring"))
        await db.commit()
        forward = AF.compute_forward_accuracy()

        await db.execute(update(SyncRun).where(SyncRun.id == run_id).values(stage="training"))
        await db.commit()
        await persist_training_rows(db)
        train = await train_all(db)
        reg = await refresh_registry(db)

        await MH.append_all(db, source="ships")
        result = dict(forward=forward.get("counts", {}), train=train, registry=reg)
        await _finish(db, run_id, result=result)
        return result
    except Exception as e:
        await _finish(db, run_id, error=str(e)[:500])
        raise
