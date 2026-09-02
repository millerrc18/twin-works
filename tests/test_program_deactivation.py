"""SCOPE-01 program deactivation and ingress-isolation contracts."""
import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db


def _seed_forecast_signature(data_source):
    from app.services import forecast_service

    programs = ("ELEV", "RAD", "AEGIS")
    return {
        program: [
            (row.serial, row.sim_finish_date, row.p50_date, row.p80_date)
            for row in forecast_service.forecast_program(
                data_source, program, programs=programs)
        ]
        for program in programs
    }


def test_deactivation_archives_candidate_and_excludes_program_at_every_active_boundary(
        tmp_path, monkeypatch):
    from app.config import settings
    from app.data import wip_tables
    from app.data.live_source import LiveMcpDataSource
    from app.data.snapshot_source import SnapshotDataSource
    from app.engines import router_registry
    from app.main import app
    from app.models import PositionState, Program
    from app.routers import dashboard as dashboard_routes
    from app.services import forecast_log_service
    from app.services import forecast_service
    from app.services import model_epoch_service
    from app.services import portfolio_service
    from app.services import position_state
    from app.services import program_service
    from app.services import sync_service
    from app.templating import program_navigation

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'deactivate.db').as_posix()}"
    original_url = settings.database_url
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(program_service, "_export_snapshot_all", lambda: None)

    async def prepare_and_deactivate():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await program_service.seed_from_routers(db)
            await position_state.seed_from_baseline(db)
            await model_epoch_service.ensure_legacy_epochs(
                db, ("ELEV", "RAD", "AEGIS"))
            created = await program_service.create_program(
                db, code="TEST4", name="Deferred program", plant="Plant 3",
                project_id="TEST4", part_nos=["TEST4-PART"],
                ops=[[100, "Observed work", "TEST-WC", 8.0, "FLOW"]],
                milestones=[["FLOW", "Observed flow"]], ceilings=[["FLOW", 100]],
                configured_planning_basis="CONTRACT_DATES", plan_label="Contract",
            )
            await model_epoch_service.transition_epoch(
                db, created["epoch_id"], to_state="OBSERVE", actor="Test admin",
                authority_role="DATA_ADMIN", rationale="Exercise scope isolation",
            )
            await position_state.upsert(
                db, "TEST4-SO", "TEST4", "T4 001", maxop=0,
                last_clock=wip_tables.AS_OF.date(), due=date(2026, 10, 1), source="test",
            )
            await db.commit()
            program_service.invalidate_cache()
            position_state.invalidate_cache()
            router_registry.rebuild()

            before = SnapshotDataSource()
            assert [row.serial for row in before.get_wip_units("TEST4")] == ["T4 001"]
            seed_before = _seed_forecast_signature(before)

            result = await program_service.deactivate_program(
                db, "TEST4", actor="Test admin",
                rationale="Return product scope to the three published programs",
            )

            stored = await db.get(Program, "TEST4")
            raw_state = await db.scalar(select(PositionState).where(
                PositionState.program == "TEST4"))
            latest = await model_epoch_service.latest_epoch(db, "TEST4")
            assert result == {
                "code": "TEST4", "changed": True,
                "archived_epoch_ids": [created["epoch_id"]],
            }
            assert stored.active is False
            assert latest.state == "ARCHIVED"
            assert raw_state.serial == "T4 001"

            after = SnapshotDataSource()
            assert after.get_wip_units("TEST4") == []
            assert after.get_shipped_units("TEST4") == []
            assert forecast_service.forecast_program(after, "TEST4") == []
            assert program_service.program_order() == ["ELEV", "RAD", "AEGIS"]
            assert sync_service.PROGRAMS() == ["ELEV", "RAD", "AEGIS"]
            assert list(router_registry.registry.programs) == ["ELEV", "RAD", "AEGIS"]
            assert [item["code"] for item in program_navigation()] == [
                "ELEV", "RAD", "AEGIS"]
            assert _seed_forecast_signature(after) == seed_before

            live = object.__new__(LiveMcpDataSource)
            live._cache = {}
            assert live.get_wip_units("TEST4") == []

            stamp = await forecast_log_service.stamp_build(db, after)
            assert stamp["programs"] == ["ELEV", "RAD", "AEGIS"]

            second = await program_service.deactivate_program(
                db, "TEST4", actor="Test admin", rationale="Idempotency check")
            assert second == {
                "code": "TEST4", "changed": False, "archived_epoch_ids": []}

    async def test_db():
        async with sessions() as db:
            yield db

    async def test_source(_db):
        return SnapshotDataSource()

    async def route_checks():
        async with sessions() as db:
            model = await portfolio_service.build_portfolio(db, SnapshotDataSource())
            assert [row["code"] for row in model["programs"]] == [
                "ELEV", "RAD", "AEGIS"]

    try:
        settings.database_url = database_url
        program_service.invalidate_cache()
        position_state.invalidate_cache()
        router_registry.rebuild()
        asyncio.run(prepare_and_deactivate())
        asyncio.run(route_checks())
        monkeypatch.setattr(dashboard_routes, "_ds", test_source)
        app.dependency_overrides[get_db] = test_db
        with TestClient(app) as client:
            portfolio = client.get("/")
            workspace = client.get("/program/TEST4/overview")
            forecast = client.get("/forecast/TEST4")
        assert portfolio.status_code == 200
        assert "Deferred program" not in portfolio.text
        assert 'href="/program/TEST4/overview"' not in portfolio.text
        assert workspace.status_code == 404
        assert forecast.status_code == 404
    finally:
        app.dependency_overrides.clear()
        settings.database_url = original_url
        program_service.invalidate_cache()
        position_state.invalidate_cache()
        router_registry.rebuild()
        asyncio.run(engine.dispose())


def test_deactivation_rejects_a_published_program(tmp_path, monkeypatch):
    from app.config import settings
    from app.engines import router_registry
    from app.services import model_epoch_service
    from app.services import program_service

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'published.db').as_posix()}"
    original_url = settings.database_url
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(program_service, "_export_snapshot_all", lambda: None)

    async def scenario():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await program_service.seed_from_routers(db)
            await model_epoch_service.ensure_legacy_epochs(db, ["ELEV"])
            with pytest.raises(
                    program_service.ProgramDeactivationError,
                    match="published program"):
                await program_service.deactivate_program(
                    db, "ELEV", actor="Test admin", rationale="Must fail")

    try:
        settings.database_url = database_url
        program_service.invalidate_cache()
        router_registry.rebuild()
        asyncio.run(scenario())
    finally:
        settings.database_url = original_url
        program_service.invalidate_cache()
        router_registry.rebuild()
        asyncio.run(engine.dispose())
