"""Read-only guarantees and validation coverage for the Marion virtual factory."""
import copy
import asyncio
import os

os.environ.setdefault("RTG_DATA_SOURCE", "snapshot")


def test_building_classification_uses_description_prefix_only():
    from app.data.floor_map import classify_building

    assert classify_building("P1 CBOX LMS") == "P1"
    assert classify_building(" P2 ASSY G500") == "P2"
    assert classify_building("P3 LAM  AERO") == "P3"
    assert classify_building("MARION 2") is None  # calendar values are not building keys


def test_reviewed_map_preserves_mobile_and_deferred_resources():
    from app.data.floor_map import load_facility_map

    facility = load_facility_map()
    fixed = {item["wc"]: item for item in facility.placements}
    mobile = {item["wc"]: item for item in facility.resources}
    assert fixed["238"]["label"] == "P3 OVEN"
    assert fixed["AEROL"]["label"] == "P3 LAM AERO"
    assert mobile["P3 QA"]["resource_kind"] == "mobile"
    assert "x" not in mobile["P3 QA"] and "y" not in mobile["P3 QA"]
    assert mobile["PRNG"]["resource_kind"] == "unplaced"


def test_floor_map_rejects_out_of_bounds_coordinates():
    from app.data.floor_map import FloorMapDataError, _validate_map

    raw = {
        "schema_version": 1,
        "floors": [{"id": "P2", "asset": "/static/test.png", "view_box": [0, 0, 10, 10]}],
        "placements": [{"wc": "X", "floor_id": "P2", "x": 11, "y": 1,
                        "label": "bad", "resource_kind": "fixed"}],
        "resources": [],
    }
    try:
        _validate_map(copy.deepcopy(raw))
    except FloorMapDataError as exc:
        assert "Out-of-bounds" in str(exc)
    else:
        raise AssertionError("Out-of-bounds coordinates were accepted")


def test_map_filter_and_read_do_not_change_golden_forecast():
    from app.data.snapshot_source import SnapshotDataSource
    from app.services.floor_map_service import build_floor_map
    from tests import golden

    before = golden._forecast_snapshot()
    model = build_floor_map(SnapshotDataSource(), program="ELEV")
    after = golden._forecast_snapshot()

    assert before == after
    assert model["program"] == "ELEV"
    qa = next(item for item in model["mobile_resources"] if item["wc"] == "P3 QA")
    assert not qa["is_relevant"]
    assert qa["telemetry"]["active_unit_count"] == 0


def test_factory_map_routes_render_full_page_and_htmx_inspector(tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database import Base, get_db
    from app.main import app
    from app.services.model_epoch_service import ensure_legacy_epochs

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'factory-map.db').as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await ensure_legacy_epochs(db, ("ELEV", "RAD", "AEGIS"))
            await db.commit()

    async def test_db():
        async with sessions() as db:
            yield db

    asyncio.run(prepare())
    app.dependency_overrides[get_db] = test_db
    client = TestClient(app)
    try:
        page = client.get("/factory-map", params={"floor": "VAMA03-F01", "program": "RAD"})
        detail = client.get("/factory-map/wc/P3%20QA", params={"program": "RAD"},
                            headers={"HX-Request": "true"})
    finally:
        client.close()
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

    assert page.status_code == 200
    assert "Marion Virtual Factory" in page.text
    assert "VAMA03 / Plant 3 / Floor 01" in page.text
    assert detail.status_code == 200
    assert 'id="factory-inspector"' in detail.text
    assert "P3 QA" in detail.text
    assert "<html" not in detail.text.lower()
