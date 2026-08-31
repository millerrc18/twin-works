"""Resource Registry and forecast Why route contracts."""
import asyncio
import os

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db


os.environ.setdefault("RTG_DATA_SOURCE", "snapshot")


def test_resource_registry_and_why_routes_render(tmp_path):
    from app.main import app
    from app.data.snapshot_source import SnapshotDataSource
    from app.routers import resources as resources_router
    from app.services.resource_profile import seed_legacy_resources

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'routes.db').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await seed_legacy_resources(db)
            await db.commit()

    asyncio.run(prepare())

    async def test_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    async def baseline_ds(_db):
        return SnapshotDataSource(use_position_state=False)
    original_ds = resources_router._ds
    resources_router._ds = baseline_ds
    client = TestClient(app)
    try:
        registry_page = client.get("/admin/resources")
        audit = client.get("/admin/resources/audit.json")
        why = client.get("/forecast/ELEV/LH%20229/why")
    finally:
        client.close()
        resources_router._ds = original_ds
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert registry_page.status_code == 200
    assert "Resource Registry" in registry_page.text
    assert "Measured actual" in registry_page.text
    assert "TwinWorks legacy model" in registry_page.text
    assert audit.status_code == 200
    assert audit.json()["retention_policy"] == "PERMANENT_APPEND_ONLY"
    assert why.status_code == 200
    assert 'id="forecast-why"' in why.text
    assert "Complete" in why.text
    assert "LEGACY:ELEV:221" in why.text
    assert "<html" not in why.text.lower()
