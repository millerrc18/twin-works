"""Dashboard + forecast routes."""
import json
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.templating import templates
from app.config import settings
from app.database import get_db
from app.data.live_source import get_data_source
from app.data import token_store
from app.services import forecast_service as FS
from app.engines.router_registry import registry

router = APIRouter()

PROG_ORDER = ("ELEV", "RAD", "AEGIS")
PROG_NAME = {"ELEV": "G500 Elevator", "RAD": "Aeronose Radome", "AEGIS": "Aegis Reflector"}


async def _ds(db: AsyncSession):
    tokens = await token_store.load_tokens(db, "ifs") if settings.data_source == "live" else None
    return get_data_source(settings.data_source, tokens)


@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    ds = await _ds(db)
    cards = []
    for p in PROG_ORDER:
        s = FS.program_summary(ds, p)
        s["name"] = PROG_NAME[p]
        cards.append(s)
    return templates.TemplateResponse(request, "dashboard.html",
                                      {"app_name": settings.app_name,
                                       "data_source": settings.data_source,
                                       "programs": cards})


@router.get("/forecast/{program}")
async def forecast(request: Request, program: str, view: str = "matrix",
                   filter: str = "all",
                   db: AsyncSession = Depends(get_db)):
    """Forecast page. view=matrix (slot-anchored grid, default) | summary (timeline).
    filter=all|behind|active (matrix only). Query params are URL-stated for QBR reproducibility."""
    ds = await _ds(db)
    program = program.upper()
    ctx = {"app_name": settings.app_name, "data_source": settings.data_source,
           "program": program, "program_name": PROG_NAME.get(program, program),
           "view": view, "flt": filter}
    if view == "summary":
        fc = FS.forecast_program(ds, program)

        def _status(f):
            # green = P80 on-time even conservative; amber = P50 ok but P80 late; red = P50 late
            if f.commit is None or f.p50 is None or f.p80 is None:
                return "amber"
            if f.p80 <= f.commit:
                return "green"
            if f.p50 <= f.commit:
                return "amber"
            return "red"

        chart = [dict(serial=f.serial,
                      sim=f.sim_finish.isoformat() if f.sim_finish else None,
                      p50=f.p50.isoformat() if f.p50 else None,
                      p80=f.p80.isoformat() if f.p80 else None,
                      target=f.commit.isoformat() if f.commit else None,
                      status=_status(f),
                      slip=f.delta_contract,
                      stalled=f.stalled) for f in fc]
        ctx.update(forecasts=fc, chart_json=json.dumps(chart))
        return templates.TemplateResponse(request, "forecast.html", ctx)
    from app.services.matrix_service import build_matrix
    from app.services import slot_service
    all_serials = sorted(u.serial for u in ds.get_wip_units(program))
    slots = None if program == "AEGIS" else await slot_service.get_slots(db, program, set(all_serials))
    ctx["m"] = build_matrix(ds, program, slots=slots, flt=filter)
    ctx["all_serials"] = all_serials
    return templates.TemplateResponse(request, "matrix.html", ctx)


@router.post("/forecast/{program}/reassign")
async def reassign_slot(program: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Inline slot reassignment (swap handling)."""
    from app.services import slot_service
    form = await request.form()
    slot_id = form.get("slot_id")
    serial = form.get("serial") or None
    await slot_service.reassign(db, slot_id, serial)
    return RedirectResponse(f"/forecast/{program.upper()}", status_code=303)
