"""RATE-01b WIP netting, shared demand, and external-load contracts."""
import asyncio
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    path = tmp_path / "rate-demand.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def test_customer_demand_nets_only_quantity_already_in_wip():
    from app.services.rate_demand import DemandRecord, WipIdentity, net_customer_demand

    result = net_customer_demand(
        records=(
            DemandRecord(
                demand_key="D1", program="RAD", variant="RADOME",
                release_month=date(2026, 10, 1), quantity=Decimal("3"),
                order_no="SO-1"),
            DemandRecord(
                demand_key="D2", program="RAD", variant="RADOME",
                release_month=date(2026, 11, 1), quantity=Decimal("2"),
                order_no=None),
        ),
        wip=(WipIdentity(
            program="RAD", order_no="SO-1", variant="RADOME",
            represented_quantity=Decimal("1")),),
        active_programs={"ELEV", "RAD", "AEGIS"},
    )

    assert [(row.demand_key, row.net_quantity) for row in result.rows] == [
        ("D1", Decimal("2")), ("D2", Decimal("2"))]
    assert result.exclusions[0].demand_key == "D1"
    assert result.exclusions[0].excluded_quantity == Decimal("1")
    assert result.exclusions[0].reason == "REPRESENTED_BY_TRACKED_WIP"


def test_demand_netting_rejects_duplicate_keys_and_cross_program_order_collision():
    from app.services.rate_demand import (
        DemandRecord, RateDemandError, WipIdentity, net_customer_demand,
    )

    duplicate = DemandRecord(
        demand_key="DUP", program="RAD", variant="RADOME",
        release_month=date(2026, 10, 1), quantity=Decimal("1"), order_no=None)
    with pytest.raises(RateDemandError, match="duplicate demand key"):
        net_customer_demand(
            records=(duplicate, duplicate), wip=(), active_programs={"RAD"})

    with pytest.raises(RateDemandError, match="belongs to ELEV"):
        net_customer_demand(
            records=(DemandRecord(
                demand_key="D1", program="RAD", variant="RADOME",
                release_month=date(2026, 10, 1), quantity=Decimal("1"),
                order_no="SHARED-SO"),),
            wip=(WipIdentity(
                program="ELEV", order_no="SHARED-SO", variant="LH",
                represented_quantity=Decimal("1")),),
            active_programs={"ELEV", "RAD"})


def test_combined_demand_keeps_other_shared_program_wip_and_scenario_units():
    from app.services.rate_demand import combine_unit_demand
    from app.services.rate_readiness import SyntheticRelease

    inherited = {
        "ELEV": [{"serial": "E1", "so": "E-SO", "maxop": 100,
                  "commit": date(2026, 10, 1), "program": "ELEV"}],
        "AEGIS": [{"serial": "A1", "so": "A-SO", "maxop": 100,
                    "commit": date(2026, 10, 1), "program": "AEGIS"}],
    }
    combined = combine_unit_demand(
        inherited_wip=inherited,
        releases=(SyntheticRelease(
            scenario_unit_id="RATE:S:ELEV:00001", program="ELEV",
            variant="LH", release_date=date(2026, 10, 5)),),
        active_programs={"ELEV", "RAD", "AEGIS"},
        required_shared_programs={"ELEV", "AEGIS"},
    )

    assert [row["serial"] for row in combined.units_by_program["ELEV"]] == [
        "E1", "RATE:S:ELEV:00001"]
    assert [row["serial"] for row in combined.units_by_program["AEGIS"]] == ["A1"]
    assert combined.inherited_unit_count == 2
    assert combined.synthetic_unit_count == 1


def test_combined_demand_rejects_missing_shared_program_wip_coverage():
    from app.services.rate_demand import RateDemandError, combine_unit_demand

    with pytest.raises(RateDemandError, match="missing required shared-program WIP"):
        combine_unit_demand(
            inherited_wip={
                "ELEV": [{"serial": "E1", "so": "E-SO", "maxop": 100,
                          "commit": date(2026, 10, 1), "program": "ELEV"}]},
            releases=(), active_programs={"ELEV", "AEGIS"},
            required_shared_programs={"ELEV", "AEGIS"})


def test_netted_customer_demand_converts_to_scenario_only_releases():
    from app.services.rate_demand import (
        DemandRecord,
        build_netted_release_calendar,
        net_customer_demand,
    )
    from app.services.rate_readiness import WorkingCalendar

    netted = net_customer_demand(
        records=(DemandRecord(
            demand_key="GAC-OCT", program="RAD", variant="RADOME",
            release_month=date(2026, 10, 1), quantity=Decimal("2")),),
        wip=(), active_programs={"RAD"})
    releases = build_netted_release_calendar(
        "CUSTOMER", netted, WorkingCalendar())

    assert len(releases) == 2
    assert releases[0].scenario_unit_id == "RATE:CUSTOMER:RAD:GAC-OCT:00001"
    assert all(row.shop_order is None for row in releases)
    assert all(row.release_date.month == 10 for row in releases)


def test_external_snapshot_excludes_tracked_and_excluded_rows_and_flags_suspect(tmp_path):
    from app.services.external_load_governance import create_external_load_snapshot
    from app.services.rate_demand import load_external_rate_demand
    from app.services.resource_registry import create_pool

    async def scenario(db):
        pool = await create_pool(
            db, code="59:SHARED", site="59", name="Shared labor",
            resource_type="LABOR", capacity_unit="HOURS")
        snapshot = await create_external_load_snapshot(
            db,
            captured_at=datetime(2026, 9, 17, 12),
            source="IFS-CRP",
            schema_version="1",
            coverage_start=date(2026, 9, 17),
            coverage_end=date(2026, 12, 31),
            tracked_programs=["ELEV", "RAD", "AEGIS"],
            quality_policy={"beyond_horizon": "BLOCK"},
            assumption_ids=[],
            rows=[
                {"pool_id": pool.id, "work_date": date(2026, 10, 1),
                 "shift": 1, "project_id": "OTHER", "order_no": "X1",
                 "part_no": "P1", "source_type": "UNTRACKED_PROJECT",
                 "load_type": "LABOR", "hours": 12, "units": None,
                 "quality": "OK", "weight": 1, "exclusion_reason": None},
                {"pool_id": pool.id, "work_date": date(2026, 10, 2),
                 "shift": 1, "project_id": "OTHER", "order_no": "X2",
                 "part_no": "P2", "source_type": "UNTRACKED_PROJECT",
                 "load_type": "LABOR", "hours": 5, "units": None,
                 "quality": "SUSPECT", "weight": 0.5, "exclusion_reason": None},
                {"pool_id": pool.id, "work_date": date(2026, 10, 3),
                 "shift": 1, "project_id": "531335", "order_no": "E-SO",
                 "part_no": "P3", "source_type": "TRACKED_PROJECT",
                 "load_type": "LABOR", "hours": 20, "units": None,
                 "quality": "OK", "weight": 1, "exclusion_reason": None},
            ],
        )
        demand = await load_external_rate_demand(
            db, snapshot.id, as_of=date(2026, 9, 17),
            horizon_end=date(2026, 12, 31))

        assert demand.hours_by_pool_shift_month == {
            (pool.id, 1, date(2026, 10, 1)): Decimal("14.5")}
        assert demand.hours_by_pool_code_month == {
            (pool.code, date(2026, 10, 1)): Decimal("14.5")}
        assert demand.excluded_rows == 1
        assert demand.readiness == "PROVISIONAL"
        assert "SUSPECT_ROWS" in demand.readiness_reasons

    _run_scenario(tmp_path, scenario)


def test_external_snapshot_with_blocked_horizon_is_unresolved(tmp_path):
    from app.services.external_load_governance import create_external_load_snapshot
    from app.services.rate_demand import load_external_rate_demand
    from app.services.resource_registry import create_pool

    async def scenario(db):
        pool = await create_pool(
            db, code="59:SHORT", site="59", name="Short coverage",
            resource_type="LABOR", capacity_unit="HOURS")
        snapshot = await create_external_load_snapshot(
            db, captured_at=datetime(2026, 9, 17, 12), source="IFS-CRP",
            schema_version="1", coverage_start=date(2026, 9, 17),
            coverage_end=date(2026, 9, 30), tracked_programs=["RAD"],
            quality_policy={"beyond_horizon": "BLOCK"}, assumption_ids=[],
            rows=[{"pool_id": pool.id, "work_date": date(2026, 9, 20),
                   "shift": 1, "project_id": "OTHER", "order_no": "X1",
                   "part_no": "P1", "source_type": "UNTRACKED_PROJECT",
                   "load_type": "LABOR", "hours": 2, "units": None,
                   "quality": "OK", "weight": 1, "exclusion_reason": None}],
        )
        demand = await load_external_rate_demand(
            db, snapshot.id, as_of=date(2026, 9, 17),
            horizon_end=date(2026, 12, 31))
        assert demand.readiness == "UNRESOLVED"
        assert "COVERAGE_END" in demand.readiness_reasons

    _run_scenario(tmp_path, scenario)
