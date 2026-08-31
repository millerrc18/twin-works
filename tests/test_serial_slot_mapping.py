"""IFS NOTE_TEXT serial resolution and current-WIP RTG slot reconciliation."""
import asyncio
from datetime import date, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def test_serial_note_parser_handles_current_ifs_formats():
    from app.data.serial_resolver import serial_from_note

    assert serial_from_note("RAD", "3700ED0001-101", "Build S/N 0524") == "524"
    assert serial_from_note("RAD", "3700ED0001-101", "SN: 0525") == "525"
    assert serial_from_note("ELEV", "72P5520501-029P01", "S / N 0240") == "LH 240"
    assert serial_from_note("ELEV", "72P5520502-029P01", "S/N-0239") == "RH 239"
    assert serial_from_note("RAD", "3700ED0001-101", "no head serial") is None


def test_live_source_resolves_new_sos_from_notes_then_persisted_sync(monkeypatch):
    from app.data.live_source import LiveMcpDataSource
    from app.services import position_state
    from app.services import program_service

    source = object.__new__(LiveMcpDataSource)
    source._as_of = datetime(2026, 8, 31, 12)
    source._cache = {}

    def query(sql):
        if "s.OBJSTATE AS STATE" in sql:
            return [
                {"SO": "1462514", "STATE": "Started", "DUE": "2026-10-19",
                 "CLOSED": None},
                {"SO": "1462515", "STATE": "Started", "DUE": "2026-10-23",
                 "CLOSED": None},
            ]
        if "MAX(CASE" in sql:
            return [
                {"SO": "1462514", "MAX_CLOSED": 50},
                {"SO": "1462515", "MAX_CLOSED": 50},
            ]
        if "MAX(c.FINISH_TIME)" in sql:
            return [
                {"SO": "1462514", "LAST_CLK": "2026-08-27"},
                {"SO": "1462515", "LAST_CLK": "2026-08-31"},
            ]
        if "NOTE_TEXT" in sql:
            return [
                {"SO": "1462514", "PART_NO": "3700ED0001-101",
                 "NOTE_TEXT": "Unit S/N 0524"},
                {"SO": "1462515", "PART_NO": "3700ED0001-101",
                 "NOTE_TEXT": None},
            ]
        raise AssertionError(sql)

    source._q = query
    monkeypatch.setattr(
        program_service, "ifs_meta",
        lambda: {"RAD": ("C48178", ("3700ED0001-101",))},
    )
    monkeypatch.setattr(
        position_state, "load_state",
        lambda: {"1462515": {"program": "RAD", "serial": "525"}},
    )

    units = source._live_wip("RAD")
    assert [(unit.so, unit.serial) for unit in units] == [
        ("1462514", "524"),
        ("1462515", "525"),
    ]


def test_get_slots_hides_completed_slots_and_keeps_current_assignments(tmp_path):
    from app.models import SlotAssignment
    from app.services.slot_service import get_slots

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'slots.db').as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add_all([
                SlotAssignment(
                    slot_id="RAD::514", program="RAD", hand="",
                    target_date=date(2026, 8, 28), serial="514"),
                SlotAssignment(
                    slot_id="RAD::508", program="RAD", hand="",
                    target_date=date(2026, 9, 4), serial="508"),
            ])
            await db.commit()
            rows = await get_slots(db, "RAD", {"524", "525"})
            assert [(row.slot_id, row.serial) for row in rows] == [
                ("RAD::524", "524"),
                ("RAD::525", "525"),
            ]

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.dispose())
