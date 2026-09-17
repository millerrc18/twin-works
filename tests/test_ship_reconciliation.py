"""Shipment detection and correction contracts."""
import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base


def test_ship_query_requires_terminal_operation_to_be_closed():
    from app.services.sync_service import SQL_CLOSED

    assert "SO_OPER_DISPATCH_LIST_CFV" in SQL_CLOSED
    assert "OPER_STATUS_CODE_DB = 90" in SQL_CLOSED


def test_unchanged_effective_ship_date_is_not_a_correction():
    from app.models import PositionState
    from app.services.sync_service import _shipment_change

    prior = PositionState(
        so="1451269", program="ELEV", serial="LH 228",
        closed=date(2026, 8, 6), pack=date(2026, 8, 1),
        last_clock=date(2026, 8, 1), source="baseline",
    )
    pulled = {
        "closed": "2026-08-06", "pack": "2026-08-01",
        "ship": "2026-08-01", "serial": "LH 228",
    }

    assert _shipment_change("1451269", pulled, prior) is None


def test_existing_early_pack_is_previewed_and_reconciled_by_shop_order(
        tmp_path, monkeypatch):
    from app.models import ForecastLog, PositionState
    from app.services import accuracy_forward, sync_service

    path = tmp_path / "ship-reconciliation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    pulled = {
        "1451436": {
            "closed": "2026-09-09",
            "due": "2026-09-03",
            "pack": "2026-09-08",
            "ship": "2026-09-08",
            "serial": "511",
        }
    }

    async def fake_client(_db):
        return object()

    monkeypatch.setattr(sync_service, "_client", fake_client)
    monkeypatch.setattr(sync_service, "_pull_closed", lambda _client, _program: pulled)
    monkeypatch.setattr(sync_service, "PROGRAMS", lambda: ["RAD"])
    monkeypatch.setattr(accuracy_forward, "forward_counts", lambda: {"RAD": 24})

    async def scenario():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(PositionState(
                so="1451436", program="RAD", serial="511", maxop=790,
                closed=date(2026, 9, 4), pack=date(2026, 9, 4), source="ifs-sync",
            ))
            db.add_all([
                ForecastLog(
                    build_date="2026-08-22", program="RAD", serial="511",
                    so="1451436", p50_date=date(2026, 9, 3),
                    actual_close=date(2026, 9, 4), error_days=-1,
                ),
                ForecastLog(
                    build_date="2026-08-24", program="RAD", serial="0511",
                    so="1451436", p50_date=date(2026, 9, 4),
                    actual_close=None, error_days=None,
                ),
            ])
            await db.commit()

            preview = await sync_service.preview_ships(db)
            assert preview["new_count"] == 1
            assert preview["would_train"] == []
            item = preview["new_by_program"]["RAD"][0]
            assert item["action"] == "corrected"
            assert item["previous_ship"] == "2026-09-04"
            assert item["ship"] == "2026-09-08"

            result = await sync_service.process_ships_fast(db)
            assert result["n"] == 1
            assert result["recorded"][0]["action"] == "corrected"

            position = await db.scalar(select(PositionState).where(
                PositionState.so == "1451436"))
            assert position.closed == date(2026, 9, 8)
            assert position.pack == date(2026, 9, 8)
            assert position.last_clock == date(2026, 9, 8)
            assert position.maxop == 790

            forecasts = (await db.execute(select(ForecastLog).where(
                ForecastLog.so == "1451436").order_by(ForecastLog.id))).scalars().all()
            assert [row.actual_close for row in forecasts] == [
                date(2026, 9, 8), date(2026, 9, 8)]
            assert [row.error_days for row in forecasts] == [-5, -4]

    try:
        asyncio.run(scenario())
    finally:
        asyncio.run(engine.dispose())
