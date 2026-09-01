"""Append-only observation quarantine lifecycle contracts."""
import asyncio
import sqlite3

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def _run_scenario(tmp_path, scenario):
    path = tmp_path / "quarantine.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db, path)
        await engine.dispose()

    asyncio.run(run())


def _conflict(so, serial):
    return {
        "so": so, "serial": serial, "state": "Started", "max_closed": 9999,
        "terminal_status": "90", "terminal_clock": None, "state_conflict": True,
    }


def test_bca_layup_policy_separates_labor_and_autoclave_occupancy():
    from app.data.bca_layup_policy import load_bca_layup_policy

    policy = load_bca_layup_policy()
    resources = {item["resource_key"]: item for item in policy["resources"]}
    assert policy["onboarding_status"] == "BLOCKED"
    assert resources["59:TRI_L_LABOR"]["requirement_mode"] == "EFFORT"
    assert resources["59:TRI_L_LABOR"]["capacity_status"] == "UNAPPROVED"
    assert resources["59:ATUP_OPERATOR"]["quantity_hours_per_unit"] == 3.7
    assert resources["59:ATUP_AUTOCLAVE"]["requirement_mode"] == "OCCUPANCY"
    assert resources["59:ATUP_AUTOCLAVE"]["minimum_hold_hours"] == 6.0
    assert resources["59:ATUP_AUTOCLAVE"]["slot_count"] is None


def test_quarantine_reconciliation_is_idempotent_and_append_only(tmp_path):
    from app.models import ObservationQuarantineEvent
    from app.services.observation_quarantine import (
        active_quarantines,
        exclude_quarantined_orders,
        reconcile_quarantines,
    )

    async def scenario(db, path):
        first = await reconcile_quarantines(
            db, stream_key="BCALAY", project_id="521938", part_no="3301ED0032-101",
            reason_code="TERMINAL_COMPLETE_STATE_OPEN",
            conflicts=[_conflict("SO-1", "42"), _conflict("SO-2", "107")],
            actor="TwinWorks audit",
        )
        await db.commit()
        assert first.opened == 2
        assert [row.order_no for row in first.active] == ["SO-1", "SO-2"]

        second = await reconcile_quarantines(
            db, stream_key="BCALAY", project_id="521938", part_no="3301ED0032-101",
            reason_code="TERMINAL_COMPLETE_STATE_OPEN",
            conflicts=[_conflict("SO-1", "42"), _conflict("SO-2", "107")],
            actor="TwinWorks audit",
        )
        await db.commit()
        assert (second.opened, second.reopened, second.resolved) == (0, 0, 0)
        assert await db.scalar(select(func.count(ObservationQuarantineEvent.id))) == 2

        third = await reconcile_quarantines(
            db, stream_key="BCALAY", project_id="521938", part_no="3301ED0032-101",
            reason_code="TERMINAL_COMPLETE_STATE_OPEN",
            conflicts=[_conflict("SO-2", "107")], actor="TwinWorks audit",
        )
        await db.commit()
        assert third.resolved == 1
        active = await active_quarantines(db, "BCALAY")
        assert [row.order_no for row in active] == ["SO-2"]
        assert exclude_quarantined_orders([
            {"order_no": "SO-1"}, {"order_no": "SO-2"},
        ], active) == [{"order_no": "SO-1"}]

        con = sqlite3.connect(path)
        try:
            for statement in (
                "UPDATE observation_quarantine_event SET actor=actor WHERE id=1",
                "DELETE FROM observation_quarantine_event WHERE id=1",
            ):
                with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                    con.execute(statement)
                con.rollback()
            with pytest.raises(sqlite3.IntegrityError, match="append-only|invalid observation"):
                con.execute(
                    "INSERT OR REPLACE INTO observation_quarantine_event "
                    "SELECT * FROM observation_quarantine_event WHERE id=1")
            con.rollback()
            with pytest.raises(sqlite3.IntegrityError, match="invalid observation quarantine"):
                con.execute("""
                    INSERT INTO observation_quarantine_event
                    (event_key,quarantine_key,sequence,stream_key,project_id,part_no,
                     order_no,reason_code,event_type,actor,evidence_json,occurred_at)
                    VALUES ('bad','bad',1,'BCALAY','521938','3301ED0032-101',
                            'BAD','TERMINAL_COMPLETE_STATE_OPEN','RESOLVE','x','{}',CURRENT_TIMESTAMP)
                """)
        finally:
            con.close()

    _run_scenario(tmp_path, scenario)
