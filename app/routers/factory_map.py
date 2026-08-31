"""Read-only Marion virtual-factory routes."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.data import token_store
from app.data.live_source import get_data_source
from app.database import get_db
from app.services.floor_map_service import build_floor_map, find_resource
from app.services import planning_basis_service as PLANNING
from app.services import program_service as PROGRAMS
from app.templating import templates


router = APIRouter()


async def _ds(db: AsyncSession):
    tokens = await token_store.load_tokens(db, "ifs") if settings.data_source == "live" else None
    return get_data_source(settings.data_source, tokens)


def _initial_resource(model: dict, floor_id: str):
    floor = next(item for item in model["floors"] if item["id"] == floor_id)
    return next((item for item in floor["markers"] if item["is_relevant"]), floor["markers"][0])


@router.get("/factory-map")
async def factory_map(request: Request, program: str = "all", floor: str | None = None,
                      db: AsyncSession = Depends(get_db)):
    published = await PLANNING.published_programs(db, PROGRAMS.program_order())
    model = build_floor_map(
        await _ds(db), program=program, floor_id=floor,
        simulation_programs=published)
    return templates.TemplateResponse(request, "factory_map.html", {
        "app_name": settings.app_name,
        "data_source": settings.data_source,
        "model": model,
        "selected_floor": next(item for item in model["floors"] if item["id"] == model["selected_floor"]),
        "initial_resource": _initial_resource(model, model["selected_floor"]),
    })


@router.get("/factory-map/wc/{wc}")
async def factory_map_resource(request: Request, wc: str, program: str = "all",
                               db: AsyncSession = Depends(get_db)):
    published = await PLANNING.published_programs(db, PROGRAMS.program_order())
    model = build_floor_map(
        await _ds(db), program=program, simulation_programs=published)
    resource = find_resource(model, wc)
    if resource is None:
        raise HTTPException(status_code=404, detail="Unknown mapped work center")
    return templates.TemplateResponse(request, "partials/factory_map_inspector.html", {
        "resource": resource,
        "data_source": settings.data_source,
    })
