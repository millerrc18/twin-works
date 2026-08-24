"""Lever / what-if routes."""
import json
from fastapi import APIRouter, Request, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.templating import templates
from app.config import settings
from app.database import get_db
from app.data.live_source import get_data_source
from app.data import token_store
from app.services import lever_service as LS

router = APIRouter()


async def _ds(db: AsyncSession):
    tokens = await token_store.load_tokens(db, "ifs") if settings.data_source == "live" else None
    return get_data_source(settings.data_source, tokens)


@router.get("/levers")
async def levers(request: Request, db: AsyncSession = Depends(get_db)):
    ds = await _ds(db)
    bottlenecks = LS.get_bottlenecks(ds)
    chart = [dict(wc=b["wc"], util=b["util_pct"] or 0, shared=b["shared"]) for b in bottlenecks]
    return templates.TemplateResponse(request, "levers.html",
                                      {"app_name": settings.app_name,
                                       "data_source": settings.data_source,
                                       "bottlenecks": bottlenecks,
                                       "presets": [(k, v[0]) for k, v in LS.PRESETS.items()],
                                       "chart_json": json.dumps(chart)})


@router.post("/levers/run")
async def levers_run(request: Request, preset: str = Form(...), db: AsyncSession = Depends(get_db)):
    ds = await _ds(db)
    res = LS.run_preset(ds, preset)
    return templates.TemplateResponse(request, "partials/lever_result.html",
                                      {"result": res})
