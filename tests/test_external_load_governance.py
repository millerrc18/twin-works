"""External-load immutability and horizon-policy gates."""
import asyncio
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'external.db').as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def test_external_snapshot_is_immutable_and_blocks_uncovered_horizon(tmp_path):
    from app.models import ExternalLoadSnapshot
    from app.services.external_load_governance import (
        assess_external_snapshot,
        create_external_load_snapshot,
    )
    from app.services.resource_registry import create_pool

    async def scenario(db):
        pool = await create_pool(
            db, code="59:EXT", site="59", name="External load pool",
            resource_type="LABOR", capacity_unit="HOURS", work_center_no="EXT",
        )
        snapshot = await create_external_load_snapshot(
            db, captured_at=datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
            source="IFS.CRP_ORDER_LOAD2", schema_version="1",
            coverage_start=date(2026, 8, 31), coverage_end=date(2026, 9, 30),
            tracked_programs=["ELEV"], quality_policy={"beyond_horizon": "BLOCK"},
            assumption_ids=[], rows=[{
                "pool_id": pool.id, "work_date": date(2026, 9, 1), "shift": 1,
                "project_id": "OTHER", "order_no": "1", "part_no": "P1",
                "source_type": "SHOP_ORDER", "load_type": "LABOR", "hours": 8,
                "units": None, "quality": "OK", "weight": 1,
                "exclusion_reason": None,
            }],
        )
        covered = await assess_external_snapshot(
            db, snapshot.id, as_of=date(2026, 8, 31), horizon_end=date(2026, 9, 30))
        assert covered.issues == ()
        blocked = await assess_external_snapshot(
            db, snapshot.id, as_of=date(2026, 8, 31), horizon_end=date(2026, 10, 1))
        assert blocked.issues[0].severity == "MISSING"
        await db.commit()
        with pytest.raises(DBAPIError):
            await db.execute(update(ExternalLoadSnapshot).where(
                ExternalLoadSnapshot.id == snapshot.id).values(coverage_end=date(2026, 10, 1)))

    _run_scenario(tmp_path, scenario)
