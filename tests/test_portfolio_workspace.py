"""Portfolio console and adaptive program-workspace route contracts."""
import asyncio
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.source import UnitRecord
from app.database import Base, get_db


class WorkspaceDataSource:
    def __init__(self):
        from app.data.snapshot_source import SnapshotDataSource

        self._baseline = SnapshotDataSource(use_position_state=False)

    def as_of(self):
        return self._baseline.as_of()

    def get_wip_units(self, program):
        if program == "TEST4":
            return [
                UnitRecord("T4 001", "T4-SO-1", 100, date(2026, 10, 1), "TEST4"),
                UnitRecord("T4 002", "T4-SO-2", None, date(2026, 10, 8), "TEST4", True),
            ]
        return self._baseline.get_wip_units(program)

    def get_shipped_units(self, program):
        return self._baseline.get_shipped_units(program)

    def get_close_date(self, so):
        return self._baseline.get_close_date(so)


def test_portfolio_and_observe_workspace_are_registry_driven(tmp_path, monkeypatch):
    from app.config import settings
    from app.engines import router_registry
    from app.main import app
    from app.routers import dashboard as routes
    from app.services import forecast_service
    from app.services import model_epoch_service
    from app.services import program_service

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'portfolio.db').as_posix()}"
    original_url = settings.database_url
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(program_service, "_export_snapshot_all", lambda: None)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await program_service.seed_from_routers(db)
            await model_epoch_service.ensure_legacy_epochs(db, ("ELEV", "RAD", "AEGIS"))
            created = await program_service.create_program(
                db, code="TEST4", name="Observed Program", plant="Plant 3",
                project_id="TEST4", part_nos=["TEST4-PART"],
                ops=[[100, "Observed work", "TEST-WC", 8.0, "FLOW"]],
                milestones=[["FLOW", "Observed flow"]], ceilings=[["FLOW", 100]],
                configured_planning_basis="CONTRACT_DATES", plan_label="Contract",
            )
            await model_epoch_service.transition_epoch(
                db, created["epoch_id"], to_state="OBSERVE", actor="Test admin",
                authority_role="DATA_ADMIN", rationale="Exercise observation workspace",
            )
            await db.commit()

    async def test_db():
        async with sessions() as db:
            yield db

    async def test_source(_db):
        return WorkspaceDataSource()

    calls = {"pooled": 0}
    original_pooled = forecast_service._pooled_sim
    from app.services import portfolio_service
    original_capacity = portfolio_service.work_center_load_rows
    calls["capacity"] = 0

    def counted_pooled(*args, **kwargs):
        calls["pooled"] += 1
        return original_pooled(*args, **kwargs)

    def counted_capacity(*args, **kwargs):
        calls["capacity"] += 1
        return original_capacity(*args, **kwargs)

    try:
        settings.database_url = database_url
        program_service.invalidate_cache()
        router_registry.rebuild()
        asyncio.run(prepare())
        program_service.invalidate_cache()
        router_registry.rebuild()
        monkeypatch.setattr(routes, "_ds", test_source)
        monkeypatch.setattr(forecast_service, "_pooled_sim", counted_pooled)
        monkeypatch.setattr(portfolio_service, "work_center_load_rows", counted_capacity)
        app.dependency_overrides[get_db] = test_db
        with TestClient(app) as client:
            portfolio = client.get("/")
            assert calls["pooled"] == 1
            assert calls["capacity"] == 1
            pages = {
                tab: client.get(f"/program/TEST4/{tab}")
                for tab in ("overview", "flow", "units", "resources", "assumptions", "history")
            }
            schedule = client.get("/program/TEST4/schedule", follow_redirects=True)

        assert portfolio.status_code == 200
        assert "Portfolio operations" in portfolio.text
        assert "Program operating picture" in portfolio.text
        assert "Observed Program" in portfolio.text
        assert 'href="/program/TEST4/overview"' in portfolio.text
        assert "published plan-slot units only" in portfolio.text
        assert "published contract-anchored units only" in portfolio.text
        assert "Shared pressure" in portfolio.text
        assert "published baseline" in portfolio.text
        assert "Maturity and review ledger" in portfolio.text

        assert all(page.status_code == 200 for page in pages.values())
        assert "Operational evidence only" not in pages["overview"].text
        assert "Observed flow" in pages["flow"].text
        assert "T4 001" in pages["units"].text
        assert "TEST-WC" in pages["resources"].text
        assert "No approved resource binding" in pages["assumptions"].text
        assert "CANDIDATE" in pages["history"].text
        for page in pages.values():
            assert "Forecast P50" not in page.text
            assert 'href="/program/TEST4/overview"' in page.text
            assert 'href="/program/TEST4/history"' in page.text

        assert schedule.status_code == 200
        assert "Schedule is not published" in schedule.text
        assert "Contract (not yet in force)" in schedule.text
        assert "Forecast P50" not in schedule.text
    finally:
        app.dependency_overrides.clear()
        settings.database_url = original_url
        program_service.invalidate_cache()
        router_registry.rebuild()
        asyncio.run(engine.dispose())
