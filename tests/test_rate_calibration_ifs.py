"""RATE-01c IFS calibration-source parsing contracts."""
from datetime import date, datetime
from decimal import Decimal

import pytest


def test_history_queries_are_ifs_compatible_and_not_silently_truncated():
    from app.services.rate_calibration_ifs import (
        first_clock_sql,
        order_labor_sql,
        order_details_sql,
        terminal_completion_sql,
        work_center_labor_sql,
    )

    starts = first_clock_sql(
        project='C48178',
        parts=('3700ED0001-101',),
        window_start=date(2025, 12, 1),
        window_end=date(2026, 9, 17),
    )
    details = order_details_sql(('SO1', 'SO2'))
    completions = terminal_completion_sql(('SO1', 'SO2'), pack_op=790)
    order_labor = order_labor_sql(('SO1', 'SO2'), cutoff=date(2026, 9, 17))
    wc_labor = work_center_labor_sql(('SO1', 'SO2'), cutoff=date(2026, 9, 17))

    for sql in (starts, details, completions, order_labor, wc_labor):
        assert 'WITH ' not in sql
        assert 'FETCH FIRST' not in sql
    assert 'HAVING MIN(c.START_TIME)' in starts
    assert 'TOTAL_ACTUAL_SPLIT_HOURS' not in details
    assert 'OPER_STATUS_CODE_DB = 90' in completions
    for sql in (order_labor, wc_labor):
        assert 'h.DATED <' in sql
        assert 'h.TRANSACTION_DATE <' in sql


def test_query_program_history_merges_staged_results_with_bounded_order_labor():
    from app.services.rate_calibration_ifs import query_program_history

    responses = iter([
        {'success': True, 'data': [
            {'ORDER_NO': 'SO1', 'ACTUAL_START': '2026-01-02 06:00:00'},
        ]},
        {'success': True, 'data': [{
            'ORDER_NO': 'SO1', 'PART_NO': '3700ED0001-101',
            'PROJECT_ID': 'C48178', 'ROUTING_REVISION': '17',
            'DUE_DATE': '2026-02-01', 'IFS_PLANNED_LABOR_HOURS': 9,
        }]},
        {'success': True, 'data': [
            {'ORDER_NO': 'SO1', 'ACTUAL_COMPLETION': '2026-01-20 12:00:00'},
        ]},
        {'success': True, 'data': [
            {'ORDER_NO': 'SO1', 'ACTUAL_LABOR_HOURS': 11},
        ]},
    ])

    class Client:
        def execute_query(self, _query):
            return next(responses)

    history = query_program_history(
        Client(), project='C48178', parts=('3700ED0001-101',), pack_op=790,
        window_start=date(2025, 12, 1), window_end=date(2026, 9, 17))

    assert history[0]['ACTUAL_START'] == '2026-01-02 06:00:00'
    assert history[0]['ACTUAL_COMPLETION'] == '2026-01-20 12:00:00'
    assert history[0]['ACTUAL_LABOR_HOURS'] == 11


def test_query_program_history_rejects_completed_order_without_bounded_labor():
    from app.services.rate_calibration import CalibrationError
    from app.services.rate_calibration_ifs import query_program_history

    responses = iter([
        {'success': True, 'data': [
            {'ORDER_NO': 'SO1', 'ACTUAL_START': '2026-01-02 06:00:00'},
        ]},
        {'success': True, 'data': [{
            'ORDER_NO': 'SO1', 'PART_NO': '3700ED0001-101',
            'PROJECT_ID': 'C48178', 'ROUTING_REVISION': '17',
            'DUE_DATE': '2026-02-01', 'IFS_PLANNED_LABOR_HOURS': 9,
        }]},
        {'success': True, 'data': [
            {'ORDER_NO': 'SO1', 'ACTUAL_COMPLETION': '2026-01-20 12:00:00'},
        ]},
        {'success': True, 'data': []},
    ])

    class Client:
        def execute_query(self, _query):
            return next(responses)

    with pytest.raises(CalibrationError, match='omitted completed orders'):
        query_program_history(
            Client(), project='C48178', parts=('3700ED0001-101',), pack_op=790,
            window_start=date(2025, 12, 1), window_end=date(2026, 9, 17))


@pytest.mark.parametrize('response, expected', [
    ({'success': False, 'error': 'bad SQL'}, 'bad SQL'),
    ({'success': True, 'data': [], 'has_more': True}, 'truncated'),
])
def test_query_program_history_rejects_failed_or_truncated_ifs_response(
        response, expected):
    from app.services.rate_calibration import CalibrationError
    from app.services.rate_calibration_ifs import query_program_history

    class Client:
        def execute_query(self, _query):
            return response

    with pytest.raises(CalibrationError, match=expected):
        query_program_history(
            Client(), project='C48178', parts=('3700ED0001-101',), pack_op=790,
            window_start=date(2025, 12, 1), window_end=date(2026, 9, 17))


def test_parse_history_keeps_open_units_for_wip_and_completed_for_labor():
    from app.services.rate_calibration_ifs import parse_history_rows

    rows = [
        {"ORDER_NO": "SO1", "PROJECT_ID": "C48178", "ROUTING_REVISION": "17",
         "ACTUAL_START": "2026-01-01 06:00:00",
         "ACTUAL_COMPLETION": "2026-01-20 12:00:00",
         "PLANNED_LABOR_HOURS": 100, "ACTUAL_LABOR_HOURS": 110},
        {"ORDER_NO": "SO2", "PROJECT_ID": "C48178", "ROUTING_REVISION": "17",
         "ACTUAL_START": "2026-01-10 06:00:00", "ACTUAL_COMPLETION": None,
         "PLANNED_LABOR_HOURS": 100, "ACTUAL_LABOR_HOURS": 50},
    ]
    orders, flows = parse_history_rows(
        "RAD", rows,
        modeled_finishes={
            "SO1": datetime(2026, 1, 22, 12),
            "SO2": datetime(2026, 2, 15, 12),
        })

    assert [row.order_no for row in orders] == ["SO1"]
    assert [row.order_no for row in flows] == ["SO1", "SO2"]
    assert flows[1].actual_completion is None
    assert orders[0].actual_labor_hours == Decimal("110")


def test_parse_history_rejects_duplicates_and_missing_modeled_finish():
    from app.services.rate_calibration import CalibrationError
    from app.services.rate_calibration_ifs import parse_history_rows

    row = {"ORDER_NO": "SO1", "PROJECT_ID": "531335", "ROUTING_REVISION": "3",
           "ACTUAL_START": "2026-01-01 06:00:00",
           "ACTUAL_COMPLETION": "2026-01-20 12:00:00",
           "PLANNED_LABOR_HOURS": 100, "ACTUAL_LABOR_HOURS": 110}
    with pytest.raises(CalibrationError, match="duplicate order"):
        parse_history_rows(
            "ELEV", [row, row], modeled_finishes={"SO1": datetime(2026, 1, 22)})
    with pytest.raises(CalibrationError, match="modeled finish"):
        parse_history_rows("ELEV", [row], modeled_finishes={})


def test_work_center_observations_include_current_route_plan_and_actuals():
    from app.services.rate_calibration_ifs import work_center_labor_observations

    rows = [
        {"WORK_CENTER_NO": "AEROA", "ACTUAL_HOURS": 25.5},
        {"WORK_CENTER_NO": "P3 QA", "ACTUAL_HOURS": 5},
    ]
    observations = work_center_labor_observations(
        program="RAD", completed_orders=2,
        route_ops=[
            (100, "A", "AEROA", 10.0, "ASSY"),
            (200, "B", "AEROA", 2.0, "ASSY"),
            (300, "C", "P3 QA", 3.0, "SHIP"),
        ],
        actual_rows=rows)

    by_wc = {row.work_center: row for row in observations}
    assert by_wc["AEROA"].planned_hours == Decimal("24.0")
    assert by_wc["AEROA"].actual_hours == Decimal("25.5")
    assert by_wc["P3 QA"].planned_hours == Decimal("6.0")
    assert by_wc["P3 QA"].actual_hours == Decimal("5")
