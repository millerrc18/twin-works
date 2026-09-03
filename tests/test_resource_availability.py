"""Append-only resource availability lifecycle and fold contracts."""
import asyncio
import json
import sqlite3
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


UTC = timezone.utc
START = datetime(2026, 9, 3, 4, tzinfo=UTC)
END = datetime(2026, 9, 26, 4, tzinfo=UTC)


def _run_scenario(tmp_path, scenario):
    path = tmp_path / "availability.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await scenario(db, path)
        await engine.dispose()

    asyncio.run(run())


def _evidence(note="Owner-confirmed provisional outage"):
    return {"source": "owner://ryan-miller", "note": note}


def test_outage_quantity_folds_against_current_baseline_and_early_return(tmp_path):
    from app.services.resource_availability import (
        fold_pool_availability,
        list_availability_events,
        open_outage,
        return_to_service,
    )
    from app.services.resource_registry import (
        add_assumption,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db, _path):
        pool = await create_pool(
            db, code="AERONOSE_SHELL_LAM_MOLD", site="59",
            name="Aeronose shell lamination molds",
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="slot_count",
            value=3, unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="DRAFT", commitment_grade="INTERNAL_ONLY",
            effective_from=START.date(), owner="Ryan Miller", approver="Ryan Miller",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=START.date(), status="DRAFT",
            capacity_scope="NET_TRACKED", slot_count=3,
            calendar_policy={"status": "UNVERIFIED"}, assumption_id=assumption.id,
        )
        opened = await open_outage(
            db, pool_id=pool.id, unavailable_quantity=1,
            effective_at=START, expected_end_at=END,
            reason_code="TOOL_SHOP",
            reason="New core and plug locating template",
            actor="Ryan Miller", authority_role="PROGRAM_OWNER",
            evidence=_evidence(),
        )
        await db.commit()
        events = await list_availability_events(db, pool_id=pool.id)

        with_three = fold_pool_availability(events, baseline_count=3)
        with_four = fold_pool_availability(events, baseline_count=4)
        assert [(row.unavailable_quantity, row.available_count)
                for row in with_three] == [(1, 2)]
        assert [(row.unavailable_quantity, row.available_count)
                for row in with_four] == [(1, 3)]
        assert with_three[0].start == START
        assert with_three[0].end == END

        returned = await return_to_service(
            db, outage_key=opened.outage_key,
            effective_at=datetime(2026, 9, 20, 14, tzinfo=UTC),
            reason="Tool returned before expected date",
            actor="Ryan Miller", authority_role="PROGRAM_OWNER",
            evidence=_evidence("Return confirmed"),
        )
        await db.commit()
        assert returned.sequence == 2
        timeline = fold_pool_availability(
            await list_availability_events(db, pool_id=pool.id), baseline_count=3)
        assert timeline[0].end == datetime(2026, 9, 20, 14, tzinfo=UTC)
        assert timeline[0].available_count == 2

    _run_scenario(tmp_path, scenario)


def test_return_to_service_accepts_on_time_and_late_actuals(tmp_path):
    from app.services.resource_availability import (
        fold_outage,
        list_availability_events,
        open_outage,
        return_to_service,
    )
    from app.services.resource_registry import (
        add_assumption,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db, _path):
        pool = await create_pool(
            db, code="RETURN_TOOL", site="59", name="Return tool",
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="slot_count",
            value=1, unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="DRAFT", commitment_grade="INTERNAL_ONLY",
            effective_from=START.date(), owner="Owner", approver="Owner",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=START.date(), status="DRAFT",
            capacity_scope="NET_TRACKED", slot_count=1,
            calendar_policy={"status": "UNVERIFIED"}, assumption_id=assumption.id,
        )
        on_time = await open_outage(
            db, pool_id=pool.id, unavailable_quantity=1,
            effective_at=START, expected_end_at=END,
            reason_code="MAINTENANCE", reason="Planned",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        await return_to_service(
            db, outage_key=on_time.outage_key, effective_at=END,
            reason="Returned on schedule", actor="Admin",
            authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        events = await list_availability_events(db, outage_key=on_time.outage_key)
        assert fold_outage(events).end == END

        late_start = datetime(2026, 10, 1, tzinfo=UTC)
        planned_end = datetime(2026, 10, 3, tzinfo=UTC)
        actual_end = datetime(2026, 10, 4, tzinfo=UTC)
        late = await open_outage(
            db, pool_id=pool.id, unavailable_quantity=1,
            effective_at=late_start, expected_end_at=planned_end,
            reason_code="REPAIR", reason="Repair",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        await return_to_service(
            db, outage_key=late.outage_key, effective_at=actual_end,
            reason="Returned one day late", actor="Admin",
            authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        events = await list_availability_events(db, outage_key=late.outage_key)
        assert fold_outage(events).end == actual_end

    _run_scenario(tmp_path, scenario)


def test_extend_and_cancel_transitions_are_validated(tmp_path):
    from app.services.resource_availability import (
        AvailabilityEventError,
        cancel_outage,
        extend_outage,
        list_availability_events,
        open_outage,
        void_outage,
    )
    from app.services.resource_registry import (
        add_assumption,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db, _path):
        pool = await create_pool(
            db, code="TEST_TOOL", site="59", name="Test tool",
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="slot_count",
            value=2, unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="DRAFT", commitment_grade="INTERNAL_ONLY",
            effective_from=START.date(), owner="Owner", approver="Owner",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=START.date(), status="DRAFT",
            capacity_scope="NET_TRACKED", slot_count=2,
            calendar_policy={"status": "UNVERIFIED"}, assumption_id=assumption.id,
        )
        future = await open_outage(
            db, pool_id=pool.id, unavailable_quantity=1,
            effective_at=datetime(2026, 10, 1, tzinfo=UTC),
            expected_end_at=datetime(2026, 10, 5, tzinfo=UTC),
            reason_code="MAINTENANCE", reason="Planned maintenance",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
            occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        cancelled = await cancel_outage(
            db, outage_key=future.outage_key, reason="Window cancelled",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
            occurred_at=datetime(2026, 9, 2, tzinfo=UTC),
        )
        assert cancelled.sequence == 2
        await db.commit()
        with pytest.raises(AvailabilityEventError, match="closed"):
            await extend_outage(
                db, outage_key=future.outage_key,
                expected_end_at=datetime(2026, 10, 6, tzinfo=UTC),
                reason="Cannot extend cancelled outage",
                actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
            )

        current = await open_outage(
            db, pool_id=pool.id, unavailable_quantity=1,
            effective_at=START, expected_end_at=END,
            reason_code="REPAIR", reason="Repair",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        extended = await extend_outage(
            db, outage_key=current.outage_key,
            expected_end_at=datetime(2026, 9, 28, 4, tzinfo=UTC),
            reason="Repair taking longer",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        assert extended.sequence == 2
        with pytest.raises(AvailabilityEventError, match="after the current end"):
            await extend_outage(
                db, outage_key=current.outage_key,
                expected_end_at=END,
                reason="Invalid shorter extension",
                actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
            )
        voided = await void_outage(
            db, outage_key=current.outage_key,
            reason="Retrospective correction: outage never occurred",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
            occurred_at=datetime(2026, 9, 30, tzinfo=UTC),
        )
        assert voided.sequence == 3
        assert len(await list_availability_events(db, pool_id=pool.id)) == 5

    _run_scenario(tmp_path, scenario)


def test_availability_events_are_append_only_in_orm_and_sqlite(tmp_path):
    from app.models import ImmutableEpochRecord, ResourceAvailabilityEvent
    from app.services.resource_availability import open_outage
    from app.services.resource_registry import (
        add_assumption,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db, path):
        pool = await create_pool(
            db, code="GUARDED_TOOL", site="59", name="Guarded tool",
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="slot_count",
            value=1, unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="DRAFT", commitment_grade="INTERNAL_ONLY",
            effective_from=START.date(), owner="Owner", approver="Owner",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=START.date(), status="DRAFT",
            capacity_scope="NET_TRACKED", slot_count=1,
            calendar_policy={"status": "UNVERIFIED"}, assumption_id=assumption.id,
        )
        row = await open_outage(
            db, pool_id=pool.id, unavailable_quantity=1,
            effective_at=START, expected_end_at=END,
            reason_code="REPAIR", reason="Repair",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        await db.commit()
        event_id = row.id

        row.reason = "Tampered"
        with pytest.raises(ImmutableEpochRecord):
            await db.flush()
        await db.rollback()
        row = await db.get(ResourceAvailabilityEvent, event_id)
        await db.delete(row)
        with pytest.raises(ImmutableEpochRecord):
            await db.flush()
        await db.rollback()

        con = sqlite3.connect(path)
        try:
            for statement in (
                "UPDATE resource_availability_event SET reason=reason WHERE id=1",
                "DELETE FROM resource_availability_event WHERE id=1",
            ):
                with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                    con.execute(statement)
                con.rollback()
            with pytest.raises(sqlite3.IntegrityError, match="append-only|invalid resource"):
                con.execute(
                    "INSERT OR REPLACE INTO resource_availability_event "
                    "SELECT * FROM resource_availability_event WHERE id=1")
            con.rollback()
            with pytest.raises(sqlite3.IntegrityError, match="exceeds effective baseline"):
                con.execute("""
                    INSERT INTO resource_availability_event
                    (event_key,outage_key,sequence,pool_id,event_type,unavailable_quantity,
                     effective_at,expected_end_at,reason_code,reason,actor,authority_role,
                     evidence_json,occurred_at)
                    VALUES ('overlap:1:OPEN','overlap',1,1,'OUTAGE_OPEN',1,
                            '2026-09-04 04:00:00','2026-09-05 04:00:00',
                            'REPAIR','overlap','x','DATA_ADMIN',
                            '{"source":"test"}',CURRENT_TIMESTAMP)
                """)
            con.rollback()
            with pytest.raises(sqlite3.IntegrityError, match="invalid resource availability"):
                con.execute("""
                    INSERT INTO resource_availability_event
                    (event_key,outage_key,sequence,pool_id,event_type,unavailable_quantity,
                     reason_code,reason,actor,authority_role,evidence_json,occurred_at)
                    VALUES ('bad','bad',1,1,'RETURN_TO_SERVICE',1,'REPAIR','bad','x',
                            'DATA_ADMIN','{}',CURRENT_TIMESTAMP)
                """)
        finally:
            con.close()

    _run_scenario(tmp_path, scenario)


def test_availability_events_are_in_permanent_audit_export(tmp_path):
    from app.services.assumption_drift import export_assumption_audit
    from app.services.resource_availability import open_outage
    from app.services.resource_registry import (
        add_assumption,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db, _path):
        pool = await create_pool(
            db, code="AUDIT_TOOL", site="59", name="Audit tool",
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="slot_count",
            value=1, unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="DRAFT", commitment_grade="INTERNAL_ONLY",
            effective_from=START.date(), owner="Owner", approver="Owner",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=START.date(), status="DRAFT",
            capacity_scope="NET_TRACKED", slot_count=1,
            calendar_policy={"status": "UNVERIFIED"}, assumption_id=assumption.id,
        )
        event = await open_outage(
            db, pool_id=pool.id, unavailable_quantity=1,
            effective_at=START, expected_end_at=END,
            reason_code="OTHER", reason="Audit coverage",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        export = await export_assumption_audit(db)
        assert export["retention_policy"] == "PERMANENT_APPEND_ONLY"
        assert [row["event_key"] for row in export["availability_events"]] == [event.event_key]
        assert json.loads(export["availability_events"][0]["evidence_json"])["source"]

    _run_scenario(tmp_path, scenario)

def test_overlapping_outage_quantities_fold_and_fail_when_they_exceed_baseline(tmp_path):
    from app.services.resource_availability import (
        AvailabilityCapacityConflict,
        fold_pool_availability,
        list_availability_events,
        open_outage,
    )
    from app.services.resource_registry import (
        add_assumption,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db, _path):
        pool = await create_pool(
            db, code="POOL_TOOL", site="59", name="Pooled tool",
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=pool.code, parameter="slot_count",
            value=3, unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="DRAFT", commitment_grade="INTERNAL_ONLY",
            effective_from=START.date(), owner="Owner", approver="Owner",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=START.date(), status="DRAFT",
            capacity_scope="NET_TRACKED", slot_count=3,
            calendar_policy={"status": "UNVERIFIED"}, assumption_id=assumption.id,
        )
        await open_outage(
            db, pool_id=pool.id, unavailable_quantity=1,
            effective_at=START, expected_end_at=END,
            reason_code="TOOL_SHOP", reason="Tool shop",
            actor="Owner", authority_role="PROGRAM_OWNER", evidence=_evidence(),
        )
        await open_outage(
            db, pool_id=pool.id, unavailable_quantity=2,
            effective_at=datetime(2026, 9, 10, 4, tzinfo=UTC),
            expected_end_at=datetime(2026, 9, 12, 4, tzinfo=UTC),
            reason_code="REPAIR", reason="Repair",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        events = await list_availability_events(db, pool_id=pool.id)
        with pytest.raises(AvailabilityCapacityConflict, match="exceeds baseline"):
            await open_outage(
                db, pool_id=pool.id, unavailable_quantity=1,
                effective_at=datetime(2026, 9, 11, 4, tzinfo=UTC),
                expected_end_at=datetime(2026, 9, 11, 12, tzinfo=UTC),
                reason_code="CALIBRATION", reason="Impossible fourth outage",
                actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
            )
        timeline = fold_pool_availability(events, baseline_count=3)
        assert [(row.start, row.end, row.available_count) for row in timeline] == [
            (START, datetime(2026, 9, 10, 4, tzinfo=UTC), 2),
            (datetime(2026, 9, 10, 4, tzinfo=UTC),
             datetime(2026, 9, 12, 4, tzinfo=UTC), 0),
            (datetime(2026, 9, 12, 4, tzinfo=UTC), END, 2),
        ]
        with pytest.raises(AvailabilityCapacityConflict, match="exceeds baseline"):
            fold_pool_availability(events, baseline_count=2)

    _run_scenario(tmp_path, scenario)


def test_open_outage_rejects_naive_time_invalid_count_and_non_tool_pool(tmp_path):
    from app.services.resource_availability import AvailabilityEventError, open_outage
    from app.services.resource_registry import (
        add_assumption,
        add_capacity_version,
        create_pool,
    )

    async def scenario(db, _path):
        tool = await create_pool(
            db, code="VALIDATION_TOOL", site="59", name="Validation tool",
            resource_type="TOOL", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=tool.code, parameter="slot_count",
            value=2, unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="DRAFT", commitment_grade="INTERNAL_ONLY",
            effective_from=START.date(), owner="Owner", approver="Owner",
        )
        await add_capacity_version(
            db, pool_id=tool.id, effective_from=START.date(), status="DRAFT",
            capacity_scope="NET_TRACKED", slot_count=2,
            calendar_policy={"status": "UNVERIFIED"}, assumption_id=assumption.id,
        )
        labor = await create_pool(
            db, code="LABOR", site="59", name="Labor",
            resource_type="LABOR", capacity_unit="HOURS",
        )
        common = dict(
            expected_end_at=END, reason_code="OTHER", reason="Validation",
            actor="Admin", authority_role="DATA_ADMIN", evidence=_evidence(),
        )
        with pytest.raises(AvailabilityEventError, match="timezone-aware UTC"):
            await open_outage(
                db, pool_id=tool.id, unavailable_quantity=1,
                effective_at=datetime(2026, 9, 3, 4), **common)
        with pytest.raises(AvailabilityEventError, match="exceeds"):
            await open_outage(
                db, pool_id=tool.id, unavailable_quantity=3,
                effective_at=START, **common)
        with pytest.raises(AvailabilityEventError, match="TOOL/SLOTS"):
            await open_outage(
                db, pool_id=labor.id, unavailable_quantity=1,
                effective_at=START, **common)

    _run_scenario(tmp_path, scenario)
