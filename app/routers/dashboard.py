"""Dashboard + forecast routes."""
import json
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.templating import templates
from app.config import settings
from app.database import get_db
from app.data.live_source import get_data_source
from app.data import token_store
from app.services import forecast_service as FS
from app.services import program_service as PSVC
from app.services import resource_explain as REX
from app.services import planning_basis_service as PLANNING

router = APIRouter()


async def _ds(db: AsyncSession):
    tokens = await token_store.load_tokens(db, "ifs") if settings.data_source == "live" else None
    return get_data_source(settings.data_source, tokens)


async def _plan_targets(db: AsyncSession, ds, program: str, planning):
    if planning.configured_planning_basis != "PLAN_SLOTS":
        return None, None
    from app.services import slot_service
    serials = {unit.serial for unit in ds.get_wip_units(program)}
    slots = await slot_service.get_slots(db, program, serials)
    return slots, {slot.serial: slot.target_date for slot in slots if slot.serial}


@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    ds = await _ds(db)
    from app.services.portfolio_service import build_portfolio
    portfolio = await build_portfolio(db, ds)
    return templates.TemplateResponse(request, "dashboard.html",
                                      {"app_name": settings.app_name,
                                       "data_source": settings.data_source,
                                       "portfolio": portfolio,
                                       "programs": portfolio["programs"]})


@router.get("/program/{program}")
async def program_home(program: str):
    return RedirectResponse(f"/program/{program.upper()}/overview", status_code=302)


@router.get("/program/{program}/{tab}")
async def program_workspace(request: Request, program: str, tab: str,
                            db: AsyncSession = Depends(get_db)):
    from app.services.portfolio_service import WORKSPACE_TABS, build_program_workspace

    program = program.upper()
    valid_tabs = {key for key, _label in WORKSPACE_TABS}
    if tab not in valid_tabs:
        raise HTTPException(status_code=404, detail="Unknown program workspace tab")
    if tab == "schedule":
        return RedirectResponse(f"/forecast/{program}", status_code=302)
    try:
        workspace = await build_program_workspace(db, await _ds(db), program, tab)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown program") from None
    return templates.TemplateResponse(request, "program_workspace.html", {
        "app_name": settings.app_name,
        "data_source": settings.data_source,
        "program": program,
        "program_name": workspace["program_name"],
        "workspace": workspace,
        "planning": workspace["planning"],
        "active_tab": tab,
    })


@router.get("/forecast/{program}")
async def forecast(request: Request, program: str, view: str = "matrix",
                   filter: str = "all", serial: str | None = None,
                   db: AsyncSession = Depends(get_db)):
    """Forecast page. view=matrix (slot-anchored grid, default) | summary (timeline).
    filter=all|behind|active (matrix only). Query params are URL-stated for QBR reproducibility."""
    ds = await _ds(db)
    program = program.upper()
    planning = await PLANNING.context_for_program(db, program)
    ctx = {"app_name": settings.app_name, "data_source": settings.data_source,
           "program": program, "program_name": PSVC.name(program),
           "view": view, "flt": filter, "selected_serial": serial,
           "active_tab": "schedule"}
    ctx["planning"] = planning
    ctx["resource_health"] = await REX.program_readiness(db, program, ds.as_of().date())
    if planning.forecast_visibility != "PUBLISHED":
        return templates.TemplateResponse(request, "schedule_locked.html", ctx)
    active_programs = await PLANNING.published_programs(db, PSVC.program_order())
    slots, plan_targets = await _plan_targets(db, ds, program, planning)
    if view == "summary":
        fc = FS.forecast_program(
            ds, program, programs=active_programs,
            planning=planning, plan_targets=plan_targets)

        def _status(f):
            # green = P80 on-time even conservative; amber = P50 ok but P80 late; red = P50 late
            if (f.comparison_target_date is None or f.p50_date is None
                    or f.p80_date is None):
                return "amber"
            if f.p80_date <= f.comparison_target_date:
                return "green"
            if f.p50_date <= f.comparison_target_date:
                return "amber"
            return "red"

        chart = [dict(serial=f.serial,
                      sim=f.sim_finish_date.isoformat() if f.sim_finish_date else None,
                      p50=f.p50_date.isoformat() if f.p50_date else None,
                      p80=f.p80_date.isoformat() if f.p80_date else None,
                      target=(f.comparison_target_date.isoformat()
                              if f.comparison_target_date else None),
                      status=_status(f),
                      slip=f.delta_to_target,
                      stalled=f.stalled) for f in fc]
        ctx.update(forecasts=fc, chart_json=json.dumps(chart))
        return templates.TemplateResponse(request, "forecast.html", ctx)
    from app.services.matrix_service import build_matrix
    all_serials = sorted(u.serial for u in ds.get_wip_units(program))
    ctx["m"] = build_matrix(
        ds, program, slots=slots, flt=filter, planning=planning,
        programs=active_programs)
    ctx["all_serials"] = all_serials
    return templates.TemplateResponse(request, "matrix.html", ctx)


@router.post("/forecast/{program}/reassign")
async def reassign_slot(program: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Inline slot reassignment (swap handling)."""
    from app.services import slot_service
    planning = await PLANNING.context_for_program(db, program)
    if (planning.forecast_visibility != "PUBLISHED"
            or planning.configured_planning_basis != "PLAN_SLOTS"):
        return RedirectResponse(f"/forecast/{program.upper()}", status_code=303)
    form = await request.form()
    slot_id = form.get("slot_id")
    serial = form.get("serial") or None
    await slot_service.reassign(db, slot_id, serial)
    return RedirectResponse(f"/forecast/{program.upper()}", status_code=303)
