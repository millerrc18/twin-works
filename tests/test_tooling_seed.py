"""TOOL-01a governed Aeronose tooling-inventory contracts."""
import asyncio
import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def test_aeronose_tooling_seed_is_draft_visible_idempotent_and_unbound(tmp_path):
    from app.models import (
        ModelAssumption,
        OperationResourceBinding,
        ResourceCapacityVersion,
        ResourcePool,
    )
    from app.services.resource_explain import list_resource_rows
    from app.services.tooling_seed import (
        AERONOSE_TOOLING,
        aeronose_tooling_inventory,
        seed_aeronose_tooling_drafts,
    )

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'tooling.db').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            first = await seed_aeronose_tooling_drafts(db)
            await db.commit()
            assert len(first["created"]) == 5
            assert first["retained"] == []
            assert first["binding_count"] == 0

            expected = {code: count for code, _name, count in AERONOSE_TOOLING}
            inventory = await aeronose_tooling_inventory(db)
            assert {row["code"]: row["slot_count"] for row in inventory} == expected
            assert all(row["present"] for row in inventory)
            assert all(row["capacity_status"] == "DRAFT" for row in inventory)
            assert all(row["assumption_status"] == "DRAFT" for row in inventory)
            assert all(row["commitment_grade"] == "INTERNAL_ONLY" for row in inventory)
            assert all(row["owner"] == "Ryan Miller, Program Manager" for row in inventory)
            assert all(row["approver"] is None for row in inventory)
            assert all(row["binding_count"] == 0 for row in inventory)

            rows = await list_resource_rows(db, date(2026, 9, 2))
            by_code = {row["code"]: row for row in rows}
            assert set(by_code) == set(expected)
            for code, count in expected.items():
                assert by_code[code]["slot_count"] == count
                assert by_code[code]["capacity_status"] == "DRAFT"
                assert by_code[code]["approval_status"] == "DRAFT"
                assert by_code[code]["readiness"] == "MISSING"
                assert by_code[code]["consumers"] == []

            counts_before = {
                "pool": await db.scalar(select(func.count(ResourcePool.id))),
                "assumption": await db.scalar(select(func.count(ModelAssumption.id))),
                "capacity": await db.scalar(select(func.count(ResourceCapacityVersion.id))),
                "binding": await db.scalar(select(func.count(OperationResourceBinding.id))),
            }
            second = await seed_aeronose_tooling_drafts(db)
            await db.commit()
            counts_after = {
                "pool": await db.scalar(select(func.count(ResourcePool.id))),
                "assumption": await db.scalar(select(func.count(ModelAssumption.id))),
                "capacity": await db.scalar(select(func.count(ResourceCapacityVersion.id))),
                "binding": await db.scalar(select(func.count(OperationResourceBinding.id))),
            }
            assert second["created"] == []
            assert second["retained"] == sorted(expected)
            assert counts_after == counts_before

            shell = await db.scalar(select(ModelAssumption).where(
                ModelAssumption.subject_key == "AERONOSE_SHELL_LAM_MOLD"))
            assert json.loads(shell.value_json) == 3
            assert "operation spans remain pending" in shell.calculation_method

        await engine.dispose()

    asyncio.run(scenario())
