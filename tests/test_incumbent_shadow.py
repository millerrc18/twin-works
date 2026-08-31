"""PLAT-01c incumbent shadow bootstrap and parity acceptance."""
import asyncio
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'incumbent.db').as_posix()}"
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db)
        await engine.dispose()

    asyncio.run(run())


def test_incumbent_candidates_are_observe_only_idempotent_and_exact(tmp_path):
    import pytest

    from app.models import AssumptionReview, ModelEpoch
    from app.data.snapshot_source import SnapshotDataSource
    from app.services.model_epoch_service import (
        ensure_incumbent_shadow_epochs,
        published_epoch,
        verify_incumbent_shadow_parity,
    )

    async def scenario(db):
        report = await verify_incumbent_shadow_parity(db)
        assert report.exact_match
        assert report.legacy_result_hash == report.shadow_result_hash
        assert report.mismatched_serials == ()
        assert set(report.programs) == {"ELEV", "RAD", "AEGIS"}
        assert all(count > 0 for count in report.unit_counts.values())
        assert report.open_review_debt > 0
        for program, candidate_id in report.candidate_epoch_ids.items():
            candidate = await db.get(ModelEpoch, candidate_id)
            assert candidate.epoch_kind == "CANDIDATE"
            assert candidate.resource_mode == "DB_SHADOW"
            published = await published_epoch(db, program)
            assert published.epoch.epoch_kind == "LEGACY_BASELINE"
            assert published.epoch.id != candidate_id
        initial_epoch_count = await db.scalar(select(func.count(ModelEpoch.id)))
        initial_review_count = await db.scalar(select(func.count(AssumptionReview.id)))
        second = await ensure_incumbent_shadow_epochs(db)
        assert {key: value.epoch.id for key, value in second.items()} == \
            report.candidate_epoch_ids
        assert await db.scalar(select(func.count(ModelEpoch.id))) == initial_epoch_count
        assert await db.scalar(select(func.count(AssumptionReview.id))) == initial_review_count

        from app.models import ResourcePool
        from app.services.model_epoch_service import EpochSelectionError
        from app.services.resource_profile import compile_profile
        pool = await db.scalar(select(ResourcePool).where(
            ResourcePool.code.like("LEGACY:ELEV:%")).limit(1))
        pool.name = "Drifted live registry name"
        with pytest.raises(EpochSelectionError, match="no longer matches"):
            await compile_profile(
                db, programs=list(report.programs),
                as_of=SnapshotDataSource(use_position_state=False).as_of(),
                horizon_end=date(2027, 3, 1),
                mode="DB_SHADOW", epoch_ids=report.candidate_epoch_ids,
            )

    _run_scenario(tmp_path, scenario)
