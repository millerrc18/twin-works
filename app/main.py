"""TwinWorks FastAPI entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.config import settings
from app.database import engine, Base
from app import models  # noqa: F401  (register tables on Base.metadata)
from app.templating import templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # Alembic is the schema authority (alembic upgrade head). create_all is an
    # idempotent safety net for a fresh clone that hasn't run migrations yet.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # load any active trained models + scored counts into the registry
    from app.database import async_session
    from ml.model.loader import refresh_registry
    async with async_session() as db:
        from app.services.model_epoch_service import assert_governance_integrity
        await assert_governance_integrity(db)
        try:
            await refresh_registry(db)
        except Exception:
            pass
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(settings.data_dir.parent / "app" / "static")), name="static")


@app.get("/health")
async def health():
    return {"ok": True, "data_source": settings.data_source, "llm": settings.llm_provider}


from app.routers.dashboard import router as dashboard_router
from app.routers.admin import router as admin_router
from app.routers.levers import router as levers_router
from app.routers.auth import router as auth_router
from app.routers.factory_map import router as factory_map_router
from app.routers.resources import router as resources_router
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(levers_router)
app.include_router(auth_router)
app.include_router(factory_map_router)
app.include_router(resources_router)
