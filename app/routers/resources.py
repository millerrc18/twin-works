"""Resource Registry and forecast-assumption explanation routes."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.data import token_store
from app.data.live_source import get_data_source
from app.database import get_db
from app.services import resource_explain as EXPLAIN
from app.services.resource_profile import seed_legacy_resources
from app.services.assumption_drift import export_assumption_audit
from app.templating import templates


router = APIRouter()


async def _ds(db: AsyncSession):
    tokens = await token_store.load_tokens(db, "ifs") if settings.data_source == "live" else None
    return get_data_source(settings.data_source, tokens)


@router.get("/admin/resources")
async def resources_page(request: Request, db: AsyncSession = Depends(get_db)):
    rows = await EXPLAIN.list_resource_rows(db, date.today())
    return templates.TemplateResponse(request, "resources.html", {
        "app_name": settings.app_name, "data_source": settings.data_source,
        "resources": rows,
    })


@router.post("/admin/resources/seed-legacy")
async def seed_resources(db: AsyncSession = Depends(get_db)):
    result = await seed_legacy_resources(db)
    await db.commit()
    return {"ok": True, **result}


@router.get("/admin/resources/audit.json")
async def resource_audit_export(db: AsyncSession = Depends(get_db)):
    return await export_assumption_audit(db)


@router.get("/admin/resources/{code:path}")
async def resource_detail(request: Request, code: str, db: AsyncSession = Depends(get_db)):
    row = await EXPLAIN.get_resource_row(db, code, date.today())
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown resource pool")
    return templates.TemplateResponse(request, "resource_detail.html", {
        "app_name": settings.app_name, "data_source": settings.data_source,
        "resource": row,
    })


@router.get("/forecast/{program}/{serial}/why")
async def forecast_why(request: Request, program: str, serial: str,
                       db: AsyncSession = Depends(get_db)):
    ds = await _ds(db)
    unit = next((row for row in ds.get_wip_units(program.upper()) if row.serial == serial), None)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unknown forecast unit")
    explanation = await EXPLAIN.explain_unit_resources(
        db, program=program, serial=serial, maxop=unit.maxop, as_of=ds.as_of().date())
    return templates.TemplateResponse(request, "partials/forecast_why.html", {
        "explanation": explanation,
    })
