"""User-facing TwinWorks operating handbook."""
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.services import handbook_service as HANDBOOK
from app.templating import templates


router = APIRouter()


def _render(request: Request, slug: str, query: str):
    selected = HANDBOOK.page(slug)
    if selected is None:
        raise HTTPException(status_code=404, detail="Unknown handbook page")
    return templates.TemplateResponse(request, "handbook.html", {
        "app_name": settings.app_name,
        "data_source": settings.data_source,
        "active_page": "handbook",
        "sections": HANDBOOK.sections(),
        "page": selected,
        "query": query.strip(),
        "results": HANDBOOK.search(query),
    })


@router.get("/handbook")
async def handbook_home(request: Request, q: str = ""):
    return _render(request, "getting-started", q)


@router.get("/handbook/{slug}")
async def handbook_page(request: Request, slug: str, q: str = ""):
    return _render(request, slug, q)
