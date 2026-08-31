"""Revision-aware, economics-preserving IFS routing discovery coverage."""
import pytest


def _routing_rows():
    # Literal revision-3 BCA economics captured from IFS on 2026-08-27.
    rows = [
        (1, "297", "Effective Documents", 0.00001, 0.001, 0, 0.001),
        (2, "297", "Change Log (NOWB)", 0.00001, 0.001, 0, 0.001),
        (6, "WAIT3", "Waiting on Inspection (NOWB)", 0, 0.00001, 0, 0.00001),
        (7, "WAIT2", "Waiting on Materials (NOWB)", 0, 0.00001, 0, 0.00001),
        (8, "WAIT1", "Waiting on Engineering (NOWB)", 0, 0.00001, 0, 0.00001),
        (9, "INSP", "General Inspection (NOWB)", 0, 0.00001, 0, 0.00001),
        (3000, "P3TRI", "Rough Trim and Resin Ridge Removal", 0, 1.6, 0, 1.6),
        (3100, "P3TRI", "Trim and Drill Setup", 0, 1.1, 0, 1.1),
        (3115, "P3 QA", "Trim and Drill Setup Inspection", 0, 0.2, 0, 0.2),
        (3200, "P3TRI", "Trim and Drill", 0, 2, 0, 2),
        (3215, "P3 QA", "Trim and Drill Inspection", 0, 0.2, 0, 0.2),
        (3300, "P3TRI", "Unload Radome", 0, 1, 0, 1),
        (3315, "P3 QA", "Off Fixture Inspection", 0, 1, 0, 1),
        (4000, "TRI A", "Drill Nutplates and Countersinks", 0, 4, 0, 4),
        (4015, "P3 QA", "Countersink Inspection", 0, 0.5, 0, 0.5),
        (4100, "TRI A", "Seal Edges, Bond Edge Protectors", 0, 5, 0, 34.2),
        (4115, "P3 QA", "LEP Hole and Void Inspection", 0, 0.5, 0, 0.5),
        (4300, "TRI A", "Nutplate, Rivets, Fill LEP Voids", 0, 4, 0, 6.8),
        (5000, "236", "Peel Ply Removal", 0, 1, 0, 0.2),
        (5015, "P3 QA", "OML Inspection", 0, 0.2, 0, 0.2),
        (5100, "236", "Surface Prep, Mask Radome", 0, 20, 0, 21),
        (5200, "236", "Prime Radome", 0, 4, 0, 5),
        (5215, "P3 QA", "Primer Inspection", 0, 0.3, 0, 0.3),
        (5300, "236", "Paint Radome, OML Stencils", 0, 8, 0, 10.5),
        (5315, "P3 QA", "Resistivity, Weight, OML Tape Test", 0, 1, 0, 1),
        (5415, "PRNG", "Electrical Testing", 0, 3, 0, 3),
        (5430, "P3NDI", "NDI Testing", 0, 0.5, 0, 0.5),
        (5500, "236", "Touch-Up Radome", 0, 6.5, 0, 4.5),
        (5515, "P3 QA", "Touch-Up Inspection", 0, 0.5, 0, 0.5),
        (6000, "3FINL", "Final Inspection", 0, 1.5, 0, 1.5),
        (7000, "235", "Radome Packing", 0, 2, 0, 3),
        (9999, "333", "TO STOCK", 0, 0.001, 0, 0.001),
    ]
    return [
        {
            "OPNO": opno, "WC": wc, "DESCR": desc, "REVISION": "3", "ALTERNATIVE": "*",
            "LABOR_SETUP": labor_setup, "LABOR_RUN": labor_run,
            "MACHINE_SETUP": machine_setup, "MACHINE_RUN": machine_run,
            "CREW_SIZE": 1, "SETUP_CREW_SIZE": 1, "RUN_TIME_CODE": "1",
            "PARALLEL": "N", "PHASE_IN": "2000-01-05T00:00:00",
            "PHASE_OUT": "2050-08-12T00:00:00", "NOTE_TEXT": None,
        }
        for opno, wc, desc, labor_setup, labor_run, machine_setup, machine_run in rows
    ]


class RoutingClient:
    def __init__(self, active_revisions=None, master_revisions=None):
        self.active_revisions = active_revisions or [
            {"REVISION": "3", "ALTERNATIVE": "*", "ORDER_COUNT": 71,
             "SAMPLE_ORDER": "1452386"},
        ]
        self.master_revisions = master_revisions or [
            {"REVISION": "1", "ALTERNATIVE": "*", "OP_COUNT": 25,
             "LABOR_HOURS": 49.503, "MACHINE_HOURS": 100.603},
            {"REVISION": "2", "ALTERNATIVE": "*", "OP_COUNT": 27,
             "LABOR_HOURS": 69.103, "MACHINE_HOURS": 103.803},
            {"REVISION": "3", "ALTERNATIVE": "*", "OP_COUNT": 32,
             "LABOR_HOURS": 69.603, "MACHINE_HOURS": 104.303},
            {"REVISION": "4", "ALTERNATIVE": "*", "OP_COUNT": 32,
             "LABOR_HOURS": 69.603, "MACHINE_HOURS": 104.303},
        ]
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        if "FROM SHOP_ORD_CFV" in query:
            return {"data": self.active_revisions}
        if "GROUP BY r.ROUTING_REVISION" in query:
            return {"data": self.master_revisions}
        if "FROM ROUTING_OPERATION_CFV" in query:
            return {"data": _routing_rows()}
        if "FROM SO_OPER_DISPATCH_LIST_CFV" in query:
            return {"data": [
                {"OPNO": 3000, "STATUS_CODE": "90", "SCHED_STATUS": "INFSCHEDULED"},
                {"OPNO": 4100, "STATUS_CODE": "40", "SCHED_STATUS": "INFSCHEDULED"},
            ]}
        raise AssertionError(f"Unexpected SQL: {query}")


def test_discovery_defaults_to_active_revision_and_preserves_bca_economics():
    from app.data.ifs_routing import discover_routing

    result = discover_routing(RoutingClient(), project_id="521938",
                              part_no="3301ED0031-101A")

    assert result["selected_revision"] == "3"
    assert result["selected_alternative"] == "*"
    assert result["reference_order"] == "1452386"
    assert result["active_order_count"] == 71
    assert len(result["routing"]) == 32
    assert result["totals"] == {
        "all_labor_hours": 69.603,
        "all_machine_hours": 104.303,
        "included_labor_hours": 69.6,
        "included_machine_hours": 104.3,
        "included_operations": 25,
        "excluded_operations": 7,
    }

    op4100 = next(op for op in result["routing"] if op["opno"] == 4100)
    assert op4100["labor_hours"] == 5.0
    assert op4100["machine_hours"] == 34.2
    assert op4100["crew_size"] == 1.0
    assert op4100["status_code"] == "40"
    assert op4100["classification"] == "production"
    assert op4100["included"] is True

    by_op = {op["opno"]: op for op in result["routing"]}
    assert by_op[1]["classification"] == "administrative"
    assert by_op[2]["nowb"] is True
    assert by_op[6]["classification"] == "waiting"
    assert by_op[9999]["classification"] == "terminal"
    assert all(by_op[opno]["included"] is False for opno in (1, 2, 6, 7, 8, 9, 9999))


def test_discovery_requires_explicit_revision_when_active_usage_is_tied():
    from app.data.ifs_routing import RoutingRevisionRequired, discover_routing

    client = RoutingClient(active_revisions=[
        {"REVISION": "3", "ALTERNATIVE": "*", "ORDER_COUNT": 5,
         "SAMPLE_ORDER": "SO3"},
        {"REVISION": "4", "ALTERNATIVE": "*", "ORDER_COUNT": 5,
         "SAMPLE_ORDER": "SO4"},
    ])

    with pytest.raises(RoutingRevisionRequired) as exc:
        discover_routing(client, project_id="521938", part_no="3301ED0031-101A")

    assert [row["revision"] for row in exc.value.revisions] == ["1", "2", "3", "4"]
    assert exc.value.active_counts == {"3/*": 5, "4/*": 5}


def test_explicit_revision_can_select_an_inactive_master_revision():
    from app.data.ifs_routing import discover_routing

    result = discover_routing(RoutingClient(), project_id="521938",
                              part_no="3301ED0031-101A", revision="4")

    assert result["selected_revision"] == "4"
    assert result["active_order_count"] == 0
    assert result["reference_order"] is None
    assert all(op["status_code"] is None for op in result["routing"])


def test_discovery_requires_exact_choice_when_alternatives_are_tied():
    from app.data.ifs_routing import RoutingRevisionRequired, discover_routing

    client = RoutingClient(
        active_revisions=[
            {"REVISION": "3", "ALTERNATIVE": "A", "ORDER_COUNT": 5,
             "SAMPLE_ORDER": "SO-A"},
            {"REVISION": "3", "ALTERNATIVE": "B", "ORDER_COUNT": 5,
             "SAMPLE_ORDER": "SO-B"},
        ],
        master_revisions=[
            {"REVISION": "3", "ALTERNATIVE": "A", "OP_COUNT": 32,
             "LABOR_HOURS": 69.6, "MACHINE_HOURS": 104.3},
            {"REVISION": "3", "ALTERNATIVE": "B", "OP_COUNT": 31,
             "LABOR_HOURS": 68.0, "MACHINE_HOURS": 103.0},
        ],
    )

    with pytest.raises(RoutingRevisionRequired) as exc:
        discover_routing(client, project_id="521938", part_no="3301ED0031-101A")

    assert [(row["revision"], row["alternative"], row["active_order_count"])
            for row in exc.value.revisions] == [("3", "A", 5), ("3", "B", 5)]

    selected = discover_routing(client, project_id="521938", part_no="3301ED0031-101A",
                                revision="3", alternative="B")
    assert selected["selected_revision"] == "3"
    assert selected["selected_alternative"] == "B"
    assert selected["reference_order"] == "SO-B"


def test_unknown_wc_gate_ignores_excluded_admin_wait_and_terminal_rows(monkeypatch):
    from app.data import ifs_routing

    monkeypatch.setattr(ifs_routing, "known_wcs", lambda: {"P3 QA"})
    routing = [
        {"wc": "WAIT1", "included": False},
        {"wc": "333", "included": False},
        {"wc": "P3 QA", "included": True},
        {"wc": "P3TRI", "included": True},
        {"wc": "221", "included": True, "nowb": True},
    ]

    assert ifs_routing.unknown_wcs(routing) == ["P3TRI", "221"]
    assert ifs_routing._classification(3800, "221", "Prep & Prime (NOWB)") == "production"


def test_admin_discovery_endpoint_returns_revision_and_economics(monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app
    from app.routers import admin

    async def no_database_needed():
        yield None

    async def fake_client(_db):
        return RoutingClient()

    monkeypatch.setattr(admin.SYNC, "_client", fake_client)
    app.dependency_overrides[get_db] = no_database_needed
    client = TestClient(app)
    try:
        response = client.post("/admin/programs/discover", json={
            "project_id": "521938", "part_no": "3301ED0031-101A",
        })
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["selected_revision"] == "3"
    assert [row["revision"] for row in body["revisions"]] == ["1", "2", "3", "4"]
    assert body["totals"]["all_labor_hours"] == 69.603
    assert body["totals"]["all_machine_hours"] == 104.303
    assert body["routing"][0]["classification"] == "administrative"


def test_program_onboarding_page_exposes_revision_and_economics_review():
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    async def no_database_needed():
        yield None

    app.dependency_overrides[get_db] = no_database_needed
    client = TestClient(app)
    try:
        response = client.get("/admin/programs")
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    for label in ("Routing revision", "Include", "Labor h", "Machine h",
                  "Class", "Status", "All-row totals", "Included totals"):
        assert label in response.text
