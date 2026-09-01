"""Read-only IFS audit for BCA layup/autoclave state and demand."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data import ifs_routing, token_store  # noqa: E402
from app.data.ifs_mcp_client import IfsMcpClient  # noqa: E402
from app.database import async_session, engine  # noqa: E402
from app.services.sync_service import _serials_from_notes  # noqa: E402


PROJECT = "521938"
PART = "3301ED0032-101"
SITE = "59"


SQL_OPEN_ORDERS = """
SELECT s.ORDER_NO AS SO, s.OBJSTATE AS STATE,
       s.ROUTING_REVISION AS REVISION, s.ROUTING_ALTERNATIVE AS ALTERNATIVE,
       TO_CHAR(s.REVISED_DUE_DATE,'YYYY-MM-DD') AS DUE,
       TO_CHAR(s.CLOSE_DATE,'YYYY-MM-DD') AS CLOSED,
       s.PART_NO AS PART_NO, s.NOTE_TEXT AS NOTE_TEXT
FROM SHOP_ORD_CFV s
WHERE s.CONTRACT = '{site}' AND s.PROJECT_ID = '{project}' AND s.PART_NO = '{part}'
  AND s.CLOSE_DATE IS NULL
ORDER BY s.ORDER_NO
"""

SQL_OPERATION_STATE = """
SELECT o.ORDER_NO AS SO,
       MAX(CASE WHEN o.OPER_STATUS_CODE_DB = 90 THEN o.OPERATION_NO END) AS MAX_CLOSED,
       MAX(CASE WHEN o.OPERATION_NO = 9999 THEN o.OPER_STATUS_CODE_DB END) AS TERMINAL_STATUS,
       MAX(CASE WHEN o.OPERATION_NO = 9999 THEN o.OPERATION_SCHED_STATUS_DB END) AS TERMINAL_SCHED_STATUS
FROM SO_OPER_DISPATCH_LIST_CFV o
WHERE o.ORDER_NO IN ({sos})
GROUP BY o.ORDER_NO
ORDER BY o.ORDER_NO
"""

SQL_CLOCK_STATE = """
SELECT c.ORDER_NO AS SO,
       TO_CHAR(MAX(c.FINISH_TIME),'YYYY-MM-DD') AS LAST_CLOCK,
       TO_CHAR(MAX(CASE WHEN c.OPERATION_NO = 9999 THEN c.FINISH_TIME END),'YYYY-MM-DD') AS TERMINAL_CLOCK
FROM GD_SHOP_FLOOR_CLOCKING c
WHERE c.ORDER_NO IN ({sos}) AND c.FINISH_TIME IS NOT NULL
GROUP BY c.ORDER_NO
ORDER BY c.ORDER_NO
"""

SQL_WC_CONFIG = """
SELECT * FROM WORK_CENTER_CFV w
WHERE w.CONTRACT = '{site}' AND w.WORK_CENTER_NO IN ('TRI L','ATUP')
ORDER BY w.WORK_CENTER_NO
"""

SQL_RECENT_LABOR = """
SELECT c.WORK_CENTER_NO AS WC,
       ROUND(SUM(NVL(c.LABOR_HOURS,0)),3) AS HOURS,
       COUNT(DISTINCT c.ORDER_NO) AS ORDERS,
       COUNT(*) AS CLOCKINGS,
       MIN(TO_CHAR(c.FINISH_TIME,'YYYY-MM-DD')) AS WINDOW_START,
       MAX(TO_CHAR(c.FINISH_TIME,'YYYY-MM-DD')) AS WINDOW_END
FROM GD_SHOP_FLOOR_CLOCKING c
WHERE c.CONTRACT = '{site}' AND c.WORK_CENTER_NO IN ('TRI L','ATUP')
  AND c.FINISH_TIME >= TO_DATE('{window_start}','YYYY-MM-DD')
  AND c.FINISH_TIME IS NOT NULL
GROUP BY c.WORK_CENTER_NO
ORDER BY c.WORK_CENTER_NO
"""

SQL_CLOCK_SAMPLE = """
SELECT * FROM GD_SHOP_FLOOR_CLOCKING c
WHERE c.CONTRACT = '{site}' AND c.WORK_CENTER_NO IN ('TRI L','ATUP')
  AND c.FINISH_TIME IS NOT NULL AND ROWNUM <= 2
"""

SQL_CURRENT_LOAD = """
SELECT o.WORK_CENTER_NO AS WC, s.PROJECT_ID AS PROJECT_ID,
       COUNT(DISTINCT o.ORDER_NO) AS ORDERS,
       ROUND(SUM(NVL(o.LABOR_SETUP_TIME,0)+NVL(o.LABOR_RUN_FACTOR,0)),3) AS LABOR_HOURS,
       ROUND(SUM(NVL(o.MACH_SETUP_TIME,0)+NVL(o.MACH_RUN_FACTOR,0)),3) AS MACHINE_HOURS
FROM SO_OPER_DISPATCH_LIST_CFV o
JOIN SHOP_ORD_CFV s ON s.ORDER_NO = o.ORDER_NO
WHERE s.CONTRACT = '{site}' AND s.CLOSE_DATE IS NULL
  AND o.WORK_CENTER_NO IN ('TRI L','ATUP')
  AND o.OPER_STATUS_CODE_DB IN (40,85,86)
GROUP BY o.WORK_CENTER_NO, s.PROJECT_ID
ORDER BY o.WORK_CENTER_NO, LABOR_HOURS DESC
"""

SQL_ELIGIBLE_BCA_LOAD = """
SELECT o.WORK_CENTER_NO AS WC,
       COUNT(DISTINCT o.ORDER_NO) AS ORDERS,
       ROUND(SUM(NVL(o.LABOR_SETUP_TIME,0)+NVL(o.LABOR_RUN_FACTOR,0)),3) AS LABOR_HOURS,
       ROUND(SUM(NVL(o.MACH_SETUP_TIME,0)+NVL(o.MACH_RUN_FACTOR,0)),3) AS MACHINE_HOURS
FROM SO_OPER_DISPATCH_LIST_CFV o
WHERE o.ORDER_NO IN ({sos}) AND o.WORK_CENTER_NO IN ('TRI L','ATUP')
  AND o.OPER_STATUS_CODE_DB IN (40,85,86)
GROUP BY o.WORK_CENTER_NO
ORDER BY o.WORK_CENTER_NO
"""


def _rows(result) -> list[dict]:
    return result.get("data", []) if isinstance(result, dict) else (result or [])


def _safe_query(client: IfsMcpClient, query: str) -> dict:
    try:
        return {"ok": True, "rows": _rows(client.execute_query(query))}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "rows": []}


def _str(value) -> str | None:
    return None if value is None else str(value)


async def audit() -> dict:
    async with async_session() as db:
        tokens = await token_store.load_tokens(db, "ifs")
    if not tokens:
        raise RuntimeError("Connect IFS before auditing BCA layup")
    client = IfsMcpClient(**tokens)
    routing = await asyncio.to_thread(
        ifs_routing.discover_routing, client,
        project_id=PROJECT, part_no=PART,
    )
    orders = _rows(client.execute_query(SQL_OPEN_ORDERS.format(
        site=SITE, project=PROJECT, part=PART)))
    sos = [str(row["SO"]) for row in orders]
    so_in = ",".join(f"'{so}'" for so in sos)
    operation_rows = _rows(client.execute_query(SQL_OPERATION_STATE.format(sos=so_in))) if sos else []
    clock_rows = _rows(client.execute_query(SQL_CLOCK_STATE.format(sos=so_in))) if sos else []
    operation_by_so = {str(row["SO"]): row for row in operation_rows}
    clock_by_so = {str(row["SO"]): row for row in clock_rows}
    serials = _serials_from_notes(client, "RAD", so_in) if sos else {}
    audited_orders = []
    for order in orders:
        so = str(order["SO"])
        operation = operation_by_so.get(so, {})
        clocks = clock_by_so.get(so, {})
        terminal_status = _str(operation.get("TERMINAL_STATUS"))
        max_closed = int(operation["MAX_CLOSED"]) if operation.get("MAX_CLOSED") is not None else None
        terminal_closed = terminal_status == "90" or max_closed == 9999
        state_conflict = terminal_closed and str(order.get("STATE") or "").lower() == "started"
        audited_orders.append({
            "so": so,
            "serial": serials.get(so),
            "state": order.get("STATE"),
            "routing_revision": _str(order.get("REVISION")),
            "routing_alternative": _str(order.get("ALTERNATIVE")),
            "due": order.get("DUE"),
            "max_closed": max_closed,
            "terminal_status": terminal_status,
            "terminal_schedule_status": operation.get("TERMINAL_SCHED_STATUS"),
            "last_clock": clocks.get("LAST_CLOCK"),
            "terminal_clock": clocks.get("TERMINAL_CLOCK"),
            "state_conflict": state_conflict,
        })
    quarantine = [row for row in audited_orders if row["state_conflict"]]
    eligible = [row for row in audited_orders if not row["state_conflict"]]
    eligible_so_in = ",".join(f"'{row['so']}'" for row in eligible)
    route_production = [row for row in routing["routing"] if row["included"]]
    route_by_wc = {}
    for row in route_production:
        route_by_wc.setdefault(row["wc"], []).append({
            "opno": row["opno"], "description": row["desc"],
            "labor_hours": row["labor_hours"], "machine_hours": row["machine_hours"],
        })
    window_start = (date.today() - timedelta(weeks=14)).isoformat()
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT,
        "part_no": PART,
        "routing": {
            "selected_revision": routing["selected_revision"],
            "selected_alternative": routing["selected_alternative"],
            "active_order_count": routing["active_order_count"],
            "row_count": len(routing["routing"]),
            "included_operations": len(route_production),
            "excluded_operations": len(routing["routing"]) - len(route_production),
            "totals": routing["totals"],
            "unknown_work_centers": ifs_routing.unknown_wcs(routing["routing"]),
            "production_by_work_center": route_by_wc,
        },
        "open_order_count": len(audited_orders),
        "quarantine_count": len(quarantine),
        "quarantine_orders": quarantine,
        "eligible_orders": eligible,
        "eligible_bca_load": _safe_query(
            client, SQL_ELIGIBLE_BCA_LOAD.format(sos=eligible_so_in)) if eligible else {
                "ok": True, "rows": [],
            },
        "work_center_configuration": _safe_query(client, SQL_WC_CONFIG.format(site=SITE)),
        "clock_schema_sample": _safe_query(client, SQL_CLOCK_SAMPLE.format(site=SITE)),
        "recent_labor": _safe_query(client, SQL_RECENT_LABOR.format(
            site=SITE, window_start=window_start)),
        "current_shared_load": _safe_query(client, SQL_CURRENT_LOAD.format(site=SITE)),
    }


async def main() -> int:
    try:
        print(json.dumps(await audit(), indent=2, sort_keys=True))
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
