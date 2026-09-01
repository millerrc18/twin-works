"""Planning-basis, target-resolution, and lifecycle-visibility contracts."""
import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db


def test_forecast_contract_separates_plan_contract_and_visibility():
    from app.data.snapshot_source import SnapshotDataSource
    from app.services import forecast_service as forecasts
    from app.services.planning_basis_service import configured_context

    ds = SnapshotDataSource(use_position_state=False)
    elev = forecasts.forecast_program(ds, "ELEV", programs=("ELEV", "RAD", "AEGIS"))[0]
    assert elev.planning_basis == "PLAN_SLOTS"
    assert elev.plan_label == "RTG"
    assert elev.contract_date is not None
    assert elev.plan_target_date is not None
    assert elev.comparison_target_date == elev.plan_target_date
    assert elev.p50_date is not None

    aegis = forecasts.forecast_program(ds, "AEGIS", programs=("ELEV", "RAD", "AEGIS"))[0]
    assert aegis.planning_basis == "CONTRACT_DATES"
    assert aegis.plan_target_date is None
    assert aegis.comparison_target_date == aegis.contract_date

    missing_plan = forecasts.forecast_program(
        ds, "ELEV", programs=("ELEV", "RAD", "AEGIS"), plan_targets={})[0]
    assert missing_plan.contract_date is not None
    assert missing_plan.comparison_target_date is None
    assert missing_plan.delta_to_target is None
    assert missing_plan.target_coverage_issue is True

    observe = forecasts.forecast_program(
        ds, "AEGIS", programs=("ELEV", "RAD", "AEGIS"),
        planning=configured_context("AEGIS", lifecycle_state="OBSERVE"))[0]
    assert observe.contract_date is not None
    assert observe.comparison_target_date is None
    assert observe.sim_finish_date is None
    assert observe.p50_date is None
    assert observe.p80_date is None
    assert observe.delta_to_target is None
    assert observe.forecast_visibility == "SUPPRESSED"


def test_routes_use_basis_labels_and_lock_draft_schedule(tmp_path, monkeypatch):
    from app.config import settings
    from app.data.snapshot_source import SnapshotDataSource
    from app.engines import router_registry as registry_module
    from app.main import app
    from app.routers import dashboard as dashboard_router
    from app.services import model_epoch_service as epochs
    from app.services import program_service as programs

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'planning.db').as_posix()}"
    original_url = settings.database_url
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(programs, "_export_snapshot_all", lambda: None)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await programs.seed_from_routers(db)
            await epochs.ensure_legacy_epochs(db, ("ELEV", "RAD", "AEGIS"))
            created = await programs.create_program(
                db, code="TEST4", name="Observed Program", plant="Plant 3",
                project_id="TEST4", part_nos=["TEST4-PART"],
                ops=[[100, "Observed work", "TEST-WC", 8.0, "ALL"]],
                configured_planning_basis="CONTRACT_DATES", plan_label="Contract",
            )
            assert created["lifecycle_state"] == "DRAFT"
            await db.commit()

    async def test_db():
        async with sessions() as db:
            yield db

    async def baseline_ds(_db):
        return SnapshotDataSource(use_position_state=False)

    try:
        settings.database_url = database_url
        programs.invalidate_cache()
        registry_module.rebuild()
        asyncio.run(prepare())
        programs.invalidate_cache()
        registry_module.rebuild()
        monkeypatch.setattr(dashboard_router, "_ds", baseline_ds)
        app.dependency_overrides[get_db] = test_db
        with TestClient(app) as client:
            contract_page = client.get("/forecast/AEGIS?view=summary")
            locked_page = client.get("/forecast/TEST4")
            dashboard_page = client.get("/")
        assert contract_page.status_code == 200
        assert "Contract target" in contract_page.text
        assert "Target (RTG)" not in contract_page.text
        assert locked_page.status_code == 200
        assert "Schedule is not published" in locked_page.text
        assert "Contract (not yet in force)" in locked_page.text
        assert "Observed Program" in locked_page.text
        observed_card = dashboard_page.text.split(
            '<a class="program-link" href="/program/TEST4/overview">', 1
        )[1].split("</tr>", 1)[0]
        assert "Observe" in observed_card
        assert "Not published" in observed_card
        assert "Model runs" not in observed_card
        assert ">behind<" not in observed_card
    finally:
        app.dependency_overrides.clear()
        settings.database_url = original_url
        programs.invalidate_cache()
        registry_module.rebuild()
        asyncio.run(engine.dispose())
