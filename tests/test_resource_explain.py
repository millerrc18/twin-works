"""Readiness and forecast-explanation behavior for resource assumptions."""
import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'explain.db').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def test_readiness_uses_worst_material_assumption_state():
    from app.services.resource_explain import aggregate_readiness
    from app.services.resource_registry import CoverageIssue

    assert aggregate_readiness([]) == "COMPLETE"
    assert aggregate_readiness([
        CoverageIssue("pool", "capacity", "PROVISIONAL", "stale")
    ]) == "PROVISIONAL"
    assert aggregate_readiness([
        CoverageIssue("pool", "capacity", "PROVISIONAL", "stale"),
        CoverageIssue("tool", "slot_count", "MISSING", "not approved"),
    ]) == "INCOMPLETE"


def test_resource_rows_expose_capacity_provenance_and_consumers(tmp_path):
    from app.services.resource_explain import list_resource_rows
    from app.services.resource_profile import seed_legacy_resources

    async def scenario(db):
        await seed_legacy_resources(db)
        rows = await list_resource_rows(db, date(2026, 8, 25))
        paint = next(row for row in rows if row["code"] == "LEGACY:ELEV:221")
        assert paint["resource_type"] == "LABOR"
        assert paint["capacity_schedule"] == {"1": 17, "2": 9, "3": 13}
        assert paint["basis"] == "MEASURED_ACTUAL"
        assert paint["approval_status"] == "APPROVED"
        assert paint["commitment_grade"] == "COMMITMENT_READY"
        assert paint["owner"] == "TwinWorks legacy model"
        assert paint["consumers"] == ["ELEV"]

    _run_scenario(tmp_path, scenario)


def test_unit_explanation_only_includes_remaining_route_resources(tmp_path):
    from app.services.resource_explain import explain_unit_resources
    from app.services.resource_profile import seed_legacy_resources

    async def scenario(db):
        await seed_legacy_resources(db)
        explanation = await explain_unit_resources(
            db, program="ELEV", serial="LH 229", maxop=3700,
            as_of=date(2026, 8, 25),
        )
        assert explanation["readiness"] == "COMPLETE"
        codes = {row["code"] for row in explanation["resources"]}
        assert "LEGACY:ELEV:221" in codes
        assert "LEGACY:ELEV:P2PCK" in codes
        assert "LEGACY:ELEV:248" not in codes
        assert all(row["basis"] and row["approval_status"] for row in explanation["resources"])

    _run_scenario(tmp_path, scenario)
