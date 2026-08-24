"""Admin routes: WI ingestion, model status, WI-constraint viewer, IFS sync (positions/ships)."""
from fastapi import APIRouter, Request, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.templating import templates
from app.config import settings
from app.database import get_db
from app.models import WIConstraint
from ml.wi.wi_service import ingest_program, PROGRAM_WIS
from ml.model.dataset import persist_training_rows
from ml.model.trainer import train_all
from ml.model.loader import refresh_registry
from ml.model.registry import registry_model
from app.services import sync_service as SYNC
from app.services import program_service as PSVC

router = APIRouter(prefix="/admin")


def PROGRAMS():
    return PSVC.program_order()


@router.post("/sync-positions")
async def sync_positions(db: AsyncSession = Depends(get_db)):
    """Button 1 — pull current WIP positions from IFS + stamp today's forecast build."""
    try:
        res = await SYNC.sync_positions(db)
    except SYNC.NotConnected:
        return JSONResponse({"ok": False, "reason": "Connect IFS first"}, status_code=400)
    except SYNC.SyncBusy as e:
        return JSONResponse({"ok": False, "reason": str(e)}, status_code=409)
    n_moved = len(res.get("moved", []))
    return {"ok": True, "moved": n_moved, "newly_stalled": res.get("newly_stalled", []),
            "unknown_serials": res.get("unknown_serials", []),
            "forecast_build": res.get("forecast_build", {})}


@router.get("/process-ships/preview")
async def preview_ships(db: AsyncSession = Depends(get_db)):
    """Read-only dry-run: how many SOs newly closed + would any program cross its train gate."""
    try:
        res = await SYNC.preview_ships(db)
    except SYNC.NotConnected:
        return JSONResponse({"ok": False, "reason": "Connect IFS first"}, status_code=400)
    return {"ok": True, **res}


async def _run_slow(run_id: int):
    """Background slow stage — its own DB session (request session is closed by then)."""
    from app.database import async_session
    async with async_session() as db:
        try:
            await SYNC.process_ships_slow(db, run_id)
        except Exception:
            pass


@router.post("/process-ships")
async def process_ships(bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Button 2 — FAST: record new closes + backfill accuracy (sync feedback);
    SLOW: rescore + retrain in the background, polled via /sync-status."""
    try:
        fast = await SYNC.process_ships_fast(db)
    except SYNC.NotConnected:
        return JSONResponse({"ok": False, "reason": "Connect IFS first"}, status_code=400)
    except SYNC.SyncBusy as e:
        return JSONResponse({"ok": False, "reason": str(e)}, status_code=409)
    bg.add_task(_run_slow, fast["run_id"])
    return {"ok": True, "recorded": fast["n"], "ships": fast["recorded"],
            "status": "rescoring + retraining in background"}


@router.get("/sync-status")
async def sync_status(db: AsyncSession = Depends(get_db)):
    run = await SYNC.current_run(db)
    if not run:
        return {"active": False, "stage": "idle"}
    return {"active": run.active, "kind": run.kind, "stage": run.stage,
            "error": run.error, "finished": run.finished_at.isoformat() if run.finished_at else None}


@router.post("/reset-positions")
async def reset_positions(db: AsyncSession = Depends(get_db)):
    """Revert PositionState to the wip_tables baseline (undo syncs)."""
    from app.services import position_state as PS
    res = await PS.reset(db)
    PS.invalidate_cache()
    return {"ok": True, **res}


@router.post("/seed-positions")
async def seed_positions(db: AsyncSession = Depends(get_db)):
    """Materialize the baseline into PositionState (one-time, before first sync)."""
    from app.services import position_state as PS
    res = await PS.seed_from_baseline(db)
    PS.invalidate_cache()
    return {"ok": True, **res}


# ---------- add-new-program onboarding ----------
@router.get("/programs")
async def programs_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Onboarding page: list existing programs + the 'Add program' form."""
    specs = PSVC.load_specs()
    existing = []
    for code in PSVC.program_order():
        s = specs.get(code, {})
        existing.append(dict(code=code, name=PSVC.name(code), plant=s.get("plant", ""),
                             project_id=s.get("project_id", ""),
                             parts=", ".join(s.get("part_nos", [])),
                             ops=len(s.get("ops", [])), cures=len(s.get("cures", [])),
                             dpas=s.get("dpas", False), threshold=PSVC.threshold(code)))
    from app.data.ifs_routing import known_wcs
    return templates.TemplateResponse(request, "programs.html", {
        "app_name": settings.app_name, "data_source": settings.data_source,
        "existing": existing, "known_wcs": sorted(known_wcs())})


@router.post("/programs/discover")
async def programs_discover(request: Request, db: AsyncSession = Depends(get_db)):
    """Pull a part's routing from IFS + flag unknown work centers. Read-only."""
    import asyncio
    body = await request.json()
    part_no = (body.get("part_no") or "").strip()
    if not part_no:
        return JSONResponse({"ok": False, "reason": "part_no required"}, status_code=400)
    try:
        client = await SYNC._client(db)          # raises NotConnected
    except SYNC.NotConnected:
        return JSONResponse({"ok": False, "reason": "Connect IFS first"}, status_code=400)
    from app.data import ifs_routing as IR
    try:
        routing = await asyncio.to_thread(IR.discover_routing, client, part_no)
    except Exception as e:
        return JSONResponse({"ok": False, "reason": f"IFS query failed: {e}"[:200]}, status_code=502)
    return {"ok": True, "routing": routing, "unknown_wcs": IR.unknown_wcs(routing),
            "n_ops": len(routing)}


@router.post("/programs/create")
async def programs_create(request: Request, db: AsyncSession = Depends(get_db)):
    """Create/replace a program from the onboarding form. Blocks on unknown WCs unless the PM
    explicitly acknowledges (allow_unknown_wcs=true)."""
    body = await request.json()
    ops = body.get("ops") or []
    if not body.get("code") or not ops:
        return JSONResponse({"ok": False, "reason": "code + at least one op required"}, status_code=400)
    from app.data.ifs_routing import unknown_wcs
    routing = [dict(opno=o[0], wc=(o[2] if len(o) > 2 else ""), desc="") for o in ops]
    unknown = unknown_wcs(routing)
    if unknown and not body.get("allow_unknown_wcs"):
        return JSONResponse({"ok": False, "reason": "unknown work centers",
                             "unknown_wcs": unknown}, status_code=409)
    try:
        res = await PSVC.create_program(
            db, code=body["code"], name=body.get("name"), plant=body.get("plant"),
            project_id=body.get("project_id"), part_nos=body.get("part_nos") or [],
            ops=ops, cures=body.get("cures"), milestones=body.get("milestones"),
            ceilings=body.get("ceilings"), crew_by_op=body.get("crew_by_op"),
            pack_op=body.get("pack_op"), ship_op=body.get("ship_op"),
            floor_op=body.get("floor_op") or 0, dpas=body.get("dpas", False),
            train_threshold=body.get("train_threshold") or 25,
            hand_split=body.get("hand_split", False), hand_map=body.get("hand_map"),
            rtg_source=body.get("rtg_source"))
    except Exception as e:
        return JSONResponse({"ok": False, "reason": str(e)[:200]}, status_code=400)
    return {"ok": True, **res}


@router.get("/model-status")
async def model_status(request: Request, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WIConstraint))).scalars().all()
    by_prog = {}
    for r in rows:
        by_prog.setdefault(r.program, []).append(r)
    models = []
    for p in PROGRAMS():
        pred = registry_model.predict(p)
        models.append(dict(program=p, mode=pred.mode, n_scored=pred.n_scored,
                           threshold=registry_model.threshold_for(p),
                           bias=round(-pred.p50_days, 1),
                           wi_constraints=len(by_prog.get(p, [])),
                           wi_files=sum(len([d for d in src.split(";") if d.strip()])
                                        for _cache, src in PROGRAM_WIS.get(p, []))))
    from app.services import model_history as MH
    from app.services import model_units as MU
    from app.data import token_store
    import json as _json
    history = await MH.history(db)
    backtest_units = MU.backtest_units()
    forward_units = MU.forward_units()
    # Connection state reflects REAL stored tokens, not the boot-time RTG_DATA_SOURCE.
    tokens = await token_store.load_tokens(db, "ifs")
    ifs_connected = bool(tokens and tokens.get("access_token")
                         and (tokens.get("refresh_token") or
                              (tokens.get("expires_at") or 0) > __import__("time").time()))
    return templates.TemplateResponse(request, "admin.html",
                                      {"app_name": settings.app_name,
                                       "data_source": settings.data_source,
                                       "ifs_connected": ifs_connected,
                                       "models": models,
                                       "constraints": by_prog,
                                       "history": history,
                                       "history_json": _json.dumps(history),
                                       "backtest_units": backtest_units,
                                       "forward_units": forward_units})


@router.post("/ingest-wi/{program}")
async def ingest_wi(program: str, db: AsyncSession = Depends(get_db)):
    program = program.upper()
    return await ingest_program(db, program)


@router.post("/rebuild-training")
async def rebuild_training(db: AsyncSession = Depends(get_db)):
    """Rebuild ml_training_row from shipped units (features + residual)."""
    res = await persist_training_rows(db)
    return dict(n_rows=res["n_rows"],
                sample=[{k: str(r.get(k)) for k in
                         ("serial", "program", "crew_at_op", "cleaned_dwell_days",
                          "residual_days")} for r in res["rows"][:3]])


@router.post("/retrain")
async def retrain(db: AsyncSession = Depends(get_db)):
    """Train quantile models per program (data-gated at threshold), then reload registry."""
    results = await train_all(db)
    reg = await refresh_registry(db)
    return dict(train=results, registry=reg,
                thresholds={p: registry_model.threshold_for(p) for p in PROGRAMS()})
