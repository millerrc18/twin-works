"""DB-active resource coverage must fail closed."""
import asyncio
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def test_db_active_profile_rejects_missing_resources(tmp_path):
    from app.data.snapshot_source import SnapshotDataSource
    from app.services.model_epoch_service import create_epoch, transition_epoch
    from app.services.resource_profile import ResourceProfileIncomplete, compile_profile

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'active-gate.db').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            epoch = await create_epoch(
                db, program="ELEV", label="Incomplete active candidate",
                epoch_kind="CANDIDATE", resource_mode="DB_ACTIVE",
                definition={"purpose": "incomplete_active_gate_test"}, created_by="Test",
            )
            await transition_epoch(
                db, epoch.id, to_state="OBSERVE", actor="Test",
                authority_role="DATA_ADMIN", rationale="Exercise fail-closed gate",
            )
            ds = SnapshotDataSource(use_position_state=False)
            with pytest.raises(ResourceProfileIncomplete) as exc:
                await compile_profile(
                    db, programs=["ELEV"], as_of=ds.as_of(),
                    horizon_end=date(2027, 3, 1), mode="DB_ACTIVE",
                    epoch_ids={"ELEV": epoch.id},
                )
            assert any(issue.parameter == "resource_binding" for issue in exc.value.issues)
        await engine.dispose()

    asyncio.run(scenario())
