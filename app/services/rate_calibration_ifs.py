'''Read-only IFS extraction helpers for RATE-01c calibration.'''
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.services.rate_calibration import (
    CalibrationError,
    CalibrationFlowUnit,
    CalibrationOrder,
    WorkCenterLabor,
)


PROJECT_BY_PROGRAM = {'ELEV': '531335', 'RAD': 'C48178'}


def _rows(result, query_name: str = 'IFS query') -> list[dict]:
    if not isinstance(result, dict):
        return result or []
    if result.get('success') is False:
        detail = result.get('error') or 'unknown error'
        raise CalibrationError(f'{query_name} failed: {detail}')
    if result.get('has_more'):
        raise CalibrationError(f'{query_name} response was truncated')
    return result.get('data', [])


def _decimal(value, field: str) -> Decimal:
    try:
        result = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        raise CalibrationError(f'{field} must be numeric') from None
    if not result.is_finite() or result < 0:
        raise CalibrationError(f'{field} must be finite and non-negative')
    return result


def _timestamp(value) -> datetime | None:
    if value in (None, ''):
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
        except ValueError as exc:
            raise CalibrationError(f'invalid IFS timestamp: {value}') from exc


def parse_history_rows(
        program: str, rows: list[dict], *, modeled_finishes: dict[str, datetime],
        ) -> tuple[tuple[CalibrationOrder, ...], tuple[CalibrationFlowUnit, ...]]:
    '''Convert IFS order aggregates to completed calibration and WIP-flow cohorts.'''
    code = program.upper()
    expected_project = PROJECT_BY_PROGRAM.get(code)
    seen = set()
    orders = []
    flows = []
    for row in sorted(rows, key=lambda item: str(item.get('ORDER_NO') or '')):
        order_no = str(row.get('ORDER_NO') or '').strip()
        if not order_no:
            raise CalibrationError('IFS history row has no order number')
        if order_no in seen:
            raise CalibrationError(f'duplicate order {order_no}')
        seen.add(order_no)
        if expected_project and str(row.get('PROJECT_ID')) != expected_project:
            raise CalibrationError(f'order {order_no} project does not match {code}')
        actual_start = _timestamp(row.get('ACTUAL_START'))
        if actual_start is None:
            raise CalibrationError(f'order {order_no} has no actual start')
        modeled = modeled_finishes.get(order_no)
        if modeled is None:
            raise CalibrationError(f'order {order_no} has no modeled finish')
        actual_completion = _timestamp(row.get('ACTUAL_COMPLETION'))
        flow = CalibrationFlowUnit(
            order_no=order_no, program=code, actual_start=actual_start,
            actual_completion=actual_completion, modeled_completion=modeled)
        flows.append(flow)
        if actual_completion is not None:
            orders.append(CalibrationOrder(
                order_no=order_no, program=code, actual_start=actual_start,
                actual_completion=actual_completion, modeled_completion=modeled,
                planned_labor_hours=_decimal(
                    row.get('MODEL_LABOR_HOURS', row.get('PLANNED_LABOR_HOURS')),
                    'modeled labor hours'),
                actual_labor_hours=_decimal(
                    row.get('ACTUAL_LABOR_HOURS'), 'actual labor hours'),
                routing_revision=str(row.get('ROUTING_REVISION') or 'UNKNOWN'),
            ))
    return tuple(orders), tuple(flows)


def work_center_labor_observations(
        *, program: str, completed_orders: int, route_ops: list,
        actual_rows: list[dict]) -> tuple[WorkCenterLabor, ...]:
    '''Build comparable current-route planned and IFS actual labor by work center.'''
    if completed_orders < 0:
        raise CalibrationError('completed_orders cannot be negative')
    planned = defaultdict(Decimal)
    for _opno, _description, work_center, hours, _milestone in route_ops:
        planned[str(work_center)] += _decimal(hours, 'route labor hours') * completed_orders
    actual = defaultdict(Decimal)
    for row in actual_rows:
        work_center = str(row.get('WORK_CENTER_NO') or '').strip()
        if not work_center:
            raise CalibrationError('IFS labor row has no work center')
        actual[work_center] += _decimal(row.get('ACTUAL_HOURS'), 'actual WC labor')
    return tuple(WorkCenterLabor(
        program=program.upper(), work_center=work_center,
        planned_hours=planned.get(work_center, Decimal(0)),
        actual_hours=actual.get(work_center, Decimal(0)),
    ) for work_center in sorted(set(planned) | set(actual)))


def first_clock_sql(*, project: str, parts: tuple[str, ...],
                    window_start: date, window_end: date) -> str:
    part_sql = ','.join(f'''{chr(39)}{part}{chr(39)}''' for part in parts)
    return f'''
SELECT c.ORDER_NO,
       TO_CHAR(MIN(c.START_TIME),'YYYY-MM-DD HH24:MI:SS') AS ACTUAL_START
FROM GD_SHOP_FLOOR_CLOCKING c
JOIN SHOP_ORD_CFV s ON s.ORDER_NO = c.ORDER_NO
WHERE s.CONTRACT = '59' AND s.PROJECT_ID = '{project}'
  AND s.PART_NO IN ({part_sql})
  AND c.CLOCKING_TYPE = 'Labor' AND c.START_TIME IS NOT NULL
GROUP BY c.ORDER_NO
HAVING MIN(c.START_TIME) >= TO_DATE('{window_start.isoformat()}','YYYY-MM-DD')
   AND MIN(c.START_TIME) < TO_DATE('{window_end.isoformat()}','YYYY-MM-DD') + 1
ORDER BY MIN(c.START_TIME), c.ORDER_NO
'''


def order_details_sql(order_numbers: tuple[str, ...]) -> str:
    if not order_numbers:
        raise CalibrationError('order detail query requires orders')
    order_sql = ','.join(
        f'''{chr(39)}{order}{chr(39)}''' for order in sorted(set(order_numbers)))
    return f'''
SELECT s.ORDER_NO, s.PART_NO, s.PROJECT_ID, s.ROUTING_REVISION,
       TO_CHAR(s.REVISED_DUE_DATE,'YYYY-MM-DD') AS DUE_DATE,
       NVL(l.TOTAL_EST_HOURS_ALL_OPS, 0) AS IFS_PLANNED_LABOR_HOURS
FROM SHOP_ORD_CFV s
LEFT JOIN GD_LABOR_HOURS_EST_ACTUAL l ON l.ORDER_NO = s.ORDER_NO
WHERE s.ORDER_NO IN ({order_sql})
ORDER BY s.ORDER_NO
'''


def terminal_completion_sql(order_numbers: tuple[str, ...], *, pack_op: int) -> str:
    if not order_numbers:
        raise CalibrationError('terminal completion query requires orders')
    order_sql = ','.join(
        f'''{chr(39)}{order}{chr(39)}''' for order in sorted(set(order_numbers)))
    return f'''
SELECT c.ORDER_NO,
       TO_CHAR(MAX(c.FINISH_TIME),'YYYY-MM-DD HH24:MI:SS') AS ACTUAL_COMPLETION
FROM GD_SHOP_FLOOR_CLOCKING c
WHERE c.ORDER_NO IN ({order_sql})
  AND c.OPERATION_NO = {pack_op}
  AND c.FINISH_TIME IS NOT NULL
  AND EXISTS (SELECT 1 FROM SO_OPER_DISPATCH_LIST_CFV o
      WHERE o.ORDER_NO = c.ORDER_NO
        AND o.OPERATION_NO = c.OPERATION_NO
        AND o.OPER_STATUS_CODE_DB = 90)
GROUP BY c.ORDER_NO
ORDER BY c.ORDER_NO
'''


def order_labor_sql(order_numbers: tuple[str, ...], *, cutoff: date) -> str:
    if not order_numbers:
        raise CalibrationError('order labor query requires orders')
    order_sql = ','.join(
        f'''{chr(39)}{order}{chr(39)}''' for order in sorted(set(order_numbers)))
    return f'''
SELECT h.ORDER_NO,
       ROUND(SUM(NVL(h.LABOR_SETUP_TIME,0) + NVL(h.LABOR_TIME,0)),3)
           AS ACTUAL_LABOR_HOURS
FROM GD_OPERATION_HISTORY_LIM h
WHERE h.ORDER_NO IN ({order_sql})
  AND h.TRANSACTION_CODE = 'LABOR_RPT'
  AND NVL(h.REVERSED_FLAG_DB,'N') = 'N'
  AND h.DATED < TO_DATE('{cutoff.isoformat()}','YYYY-MM-DD') + 1
  AND h.TRANSACTION_DATE < TO_DATE('{cutoff.isoformat()}','YYYY-MM-DD') + 1
GROUP BY h.ORDER_NO
ORDER BY h.ORDER_NO
'''


def work_center_labor_sql(order_numbers: tuple[str, ...], *, cutoff: date) -> str:
    if not order_numbers:
        raise CalibrationError('work-center labor query requires completed orders')
    order_sql = ','.join(f'''{chr(39)}{order}{chr(39)}''' for order in sorted(set(order_numbers)))
    return f'''
SELECT h.WORK_CENTER_NO,
       ROUND(SUM(NVL(h.LABOR_SETUP_TIME,0) + NVL(h.LABOR_TIME,0)),3) AS ACTUAL_HOURS
FROM GD_OPERATION_HISTORY_LIM h
WHERE h.ORDER_NO IN ({order_sql})
  AND h.TRANSACTION_CODE = 'LABOR_RPT'
  AND NVL(h.REVERSED_FLAG_DB,'N') = 'N'
  AND h.DATED < TO_DATE('{cutoff.isoformat()}','YYYY-MM-DD') + 1
  AND h.TRANSACTION_DATE < TO_DATE('{cutoff.isoformat()}','YYYY-MM-DD') + 1
GROUP BY h.WORK_CENTER_NO
ORDER BY h.WORK_CENTER_NO
'''


def query_program_history(
        client, *, project: str, parts: tuple[str, ...], pack_op: int,
        window_start: date, window_end: date) -> list[dict]:
    starts = _rows(client.execute_query(first_clock_sql(
        project=project, parts=parts,
        window_start=window_start, window_end=window_end)), 'first-clock query')
    if not starts:
        return []
    order_numbers = tuple(str(row['ORDER_NO']) for row in starts)
    details = _rows(client.execute_query(order_details_sql(order_numbers)),
                    'order detail query')
    completions = _rows(client.execute_query(terminal_completion_sql(
        order_numbers, pack_op=pack_op)), 'terminal completion query')
    labor = _rows(client.execute_query(order_labor_sql(
        order_numbers, cutoff=window_end)), 'bounded order labor query')
    details_by_order = {str(row['ORDER_NO']): row for row in details}
    completion_by_order = {
        str(row['ORDER_NO']): row.get('ACTUAL_COMPLETION')
        for row in completions
    }
    labor_by_order = {
        str(row['ORDER_NO']): row.get('ACTUAL_LABOR_HOURS')
        for row in labor
    }
    missing = sorted(set(order_numbers) - set(details_by_order))
    if missing:
        raise CalibrationError(f'order detail query omitted orders: {missing}')
    missing_labor = sorted(set(completion_by_order) - set(labor_by_order))
    if missing_labor:
        raise CalibrationError(
            f'bounded order labor query omitted completed orders: {missing_labor}')
    history = []
    for start in starts:
        order_no = str(start['ORDER_NO'])
        history.append({
            **details_by_order[order_no],
            'ACTUAL_START': start.get('ACTUAL_START'),
            'ACTUAL_COMPLETION': completion_by_order.get(order_no),
            'ACTUAL_LABOR_HOURS': labor_by_order.get(order_no, 0),
        })
    return history
