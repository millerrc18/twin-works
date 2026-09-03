"""Read-only IFS evidence audit for Aeronose tooling acquisition and turnover."""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data import ifs_routing, token_store  # noqa: E402
from app.data.ifs_mcp_client import IfsMcpClient  # noqa: E402
from app.database import async_session, engine  # noqa: E402
from app.services.sync_service import _serials_from_notes  # noqa: E402


PROJECT = "C48178"
TOP_PART = "3700ED0001-101"
SUBRING_PART = "3700ED0001-101SUBRING"
CORE_PART = "3700COREKIT"
SITE = "59"
TOOLING_OPERATIONS = (
    50, 90, 130, 170, 210, 250, 290, 330, 370, 410, 450, 490, 530, 570,
    580, 600, 605, 608, 610, 612, 615, 620, 621, 625, 630, 635, 640, 650,
    660, 670, 680, 690, 695, 700, 705, 710, 720, 775,
)

SQL_ORDERS = """
SELECT s.ORDER_NO AS SO, s.OBJSTATE AS STATE, s.PART_NO AS PART_NO,
       s.ROUTING_REVISION AS REVISION, s.ROUTING_ALTERNATIVE AS ALTERNATIVE,
       TO_CHAR(s.CLOSE_DATE,'YYYY-MM-DD') AS CLOSED, s.NOTE_TEXT AS NOTE_TEXT
FROM SHOP_ORD_CFV s
WHERE s.CONTRACT = '{site}' AND s.PROJECT_ID = '{project}'
  AND s.PART_NO = '{part}'
  AND (s.CLOSE_DATE IS NULL OR s.CLOSE_DATE >= TO_DATE('{window_start}','YYYY-MM-DD'))
ORDER BY NVL(s.CLOSE_DATE, SYSDATE + 1) DESC, s.ORDER_NO DESC
"""

SQL_CLOCKINGS = """
SELECT c.ORDER_NO AS SO, c.OPERATION_NO AS OPNO, c.WORK_CENTER_NO AS WC,
       TO_CHAR(MIN(c.START_TIME),'YYYY-MM-DD HH24:MI:SS') AS FIRST_START,
       TO_CHAR(MAX(c.FINISH_TIME),'YYYY-MM-DD HH24:MI:SS') AS LAST_FINISH,
       ROUND(SUM(NVL(c.DURATION,0)),3) AS DURATION,
       ROUND(SUM(NVL(c.TOTAL_DURATION,0)),3) AS TOTAL_DURATION,
       COUNT(*) AS CLOCKINGS
FROM GD_SHOP_FLOOR_CLOCKING c
JOIN SHOP_ORD_CFV s ON s.ORDER_NO = c.ORDER_NO
WHERE s.CONTRACT = '{site}' AND s.PROJECT_ID = '{project}'
  AND s.PART_NO = '{part}'
  AND c.OPERATION_NO = {operation}
  AND (c.START_TIME >= TO_DATE('{window_start}','YYYY-MM-DD')
       OR c.FINISH_TIME >= TO_DATE('{window_start}','YYYY-MM-DD'))
GROUP BY c.ORDER_NO, c.OPERATION_NO, c.WORK_CENTER_NO
ORDER BY FIRST_START, c.ORDER_NO, c.OPERATION_NO
"""

SQL_SUBRING_ROUTING_SEARCH = """
SELECT r.PART_NO AS PART_NO, r.ROUTING_REVISION AS REVISION,
       r.ALTERNATIVE_NO AS ALTERNATIVE, r.OPERATION_NO AS OPNO,
       r.WORK_CENTER_NO AS WC, r.OPERATION_DESCRIPTION AS DESCRIPTION
FROM ROUTING_OPERATION_CFV r
WHERE r.CONTRACT = '{site}' AND r.BOM_TYPE_DB = 'M'
  AND r.PART_NO LIKE '3700%'
  AND r.OPERATION_NO IN (600,605,608,610,612,615)
  AND (UPPER(r.OPERATION_DESCRIPTION) LIKE '%RING%'
       OR UPPER(r.OPERATION_DESCRIPTION) LIKE '%JURY%'
       OR UPPER(r.OPERATION_DESCRIPTION) LIKE '%SPLICE%')
ORDER BY r.PART_NO, r.ROUTING_REVISION, r.ALTERNATIVE_NO, r.OPERATION_NO
"""

SQL_CORE_ROUTING = """
SELECT r.ROUTING_REVISION AS REVISION, r.ALTERNATIVE_NO AS ALTERNATIVE,
       r.OPERATION_NO AS OPNO, r.WORK_CENTER_NO AS WC,
       r.OPERATION_DESCRIPTION AS DESCRIPTION,
       r.PHASE_IN_DATE AS PHASE_IN, r.PHASE_OUT_DATE AS PHASE_OUT
FROM ROUTING_OPERATION_CFV r
WHERE r.CONTRACT = '{site}' AND r.PART_NO = '{part}' AND r.BOM_TYPE_DB = 'M'
ORDER BY r.ROUTING_REVISION, r.ALTERNATIVE_NO, r.OPERATION_NO
"""


def _rows(result) -> list[dict]:
    return result.get("data", []) if isinstance(result, dict) else (result or [])


def _parse_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(sep=" ") if value else None


def _clock_index(rows: list[dict]) -> dict[str, dict[int, dict]]:
    result: dict[str, dict[int, dict]] = {}
    for row in rows:
        result.setdefault(str(row["SO"]), {})[int(row["OPNO"])] = row
    return result


def _interval(
    operations: dict[int, dict],
    *,
    acquire_ops: tuple[int, ...],
    release_op: int,
    release_boundary: str = "finish",
) -> dict | None:
    acquire = next((operations.get(opno) for opno in acquire_ops if operations.get(opno)), None)
    release = operations.get(release_op)
    if not acquire or not release:
        return None
    started = _parse_timestamp(acquire.get("FIRST_START"))
    finished = _parse_timestamp(
        release.get("FIRST_START") if release_boundary == "start" else release.get("LAST_FINISH")
    )
    if not started or not finished or finished < started:
        return None
    return {
        "acquire_op": int(acquire["OPNO"]),
        "release_op": release_op,
        "release_boundary": release_boundary,
        "started": started,
        "finished": finished,
        "elapsed_hours": round((finished - started).total_seconds() / 3600, 3),
    }


def _summarize_intervals(intervals: list[dict], capacity: int | None) -> dict:
    if not intervals:
        return {"count": 0, "max_concurrent": 0, "reuse_gaps_hours": []}
    events = []
    for row in intervals:
        events.append((row["started"], 1))
        events.append((row["finished"], -1))
    active = 0
    maximum = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)

    summary = {
        "count": len(intervals),
        "max_concurrent": maximum,
        "configured_slots": capacity,
        "elapsed_hours_median": round(statistics.median(row["elapsed_hours"] for row in intervals), 3),
    }
    if capacity is None:
        return summary

    slot_release: list[datetime | None] = [None] * capacity
    gaps: list[float] = []
    over_capacity = 0
    for row in sorted(intervals, key=lambda item: (item["started"], item["so"])):
        available = [
            (released or datetime.min, index)
            for index, released in enumerate(slot_release)
            if released is None or released <= row["started"]
        ]
        if not available:
            over_capacity += 1
            index = min(range(capacity), key=lambda idx: slot_release[idx] or datetime.min)
        else:
            _, index = min(available)
        prior = slot_release[index]
        if prior is not None and prior <= row["started"]:
            gaps.append(round((row["started"] - prior).total_seconds() / 3600, 3))
        slot_release[index] = max(row["finished"], prior or row["finished"])

    fit = over_capacity == 0 and maximum <= capacity
    summary.update({
        "intervals_over_capacity": over_capacity,
        "clock_span_fits_owner_count": fit,
        "reuse_gaps_hours": {
            "valid": fit,
            "count": len(gaps) if fit else 0,
            "minimum": min(gaps) if fit and gaps else None,
            "median": round(statistics.median(gaps), 3) if fit and gaps else None,
        },
    })
    return summary


def _serialize_interval(row: dict) -> dict:
    return {**row, "started": _iso(row["started"]), "finished": _iso(row["finished"])}


async def audit(window_start: str) -> dict:
    async with async_session() as db:
        tokens = await token_store.load_tokens(db, "ifs")
    if not tokens:
        raise RuntimeError("Connect IFS before auditing Aeronose tooling")
    client = IfsMcpClient(**tokens)

    routing = await asyncio.to_thread(
        ifs_routing.discover_routing,
        client,
        project_id=PROJECT,
        part_no=TOP_PART,
    )
    subring_routing = await asyncio.to_thread(
        ifs_routing.discover_routing,
        client,
        project_id=PROJECT,
        part_no=SUBRING_PART,
    )
    core_routing = await asyncio.to_thread(
        ifs_routing.discover_routing,
        client,
        project_id=PROJECT,
        part_no=CORE_PART,
    )
    top_orders = _rows(client.execute_query(SQL_ORDERS.format(
        site=SITE,
        project=PROJECT,
        part=TOP_PART,
        window_start=window_start,
    )))
    subring_orders = _rows(client.execute_query(SQL_ORDERS.format(
        site=SITE,
        project=PROJECT,
        part=SUBRING_PART,
        window_start=window_start,
    )))
    core_orders = _rows(client.execute_query(SQL_ORDERS.format(
        site=SITE,
        project=PROJECT,
        part=CORE_PART,
        window_start=window_start,
    )))
    so_in = ",".join(f"'{row['SO']}'" for row in top_orders)
    serials = _serials_from_notes(client, "RAD", so_in) if so_in else {}

    top_clockings = []
    for opno in TOOLING_OPERATIONS:
        top_clockings.extend(_rows(client.execute_query(SQL_CLOCKINGS.format(
            site=SITE,
            project=PROJECT,
            part=TOP_PART,
            operation=opno,
            window_start=window_start,
        ))))
    clocks = _clock_index(top_clockings)

    core_clockings = []
    for opno in (600, 700):
        core_clockings.extend(_rows(client.execute_query(SQL_CLOCKINGS.format(
            site=SITE,
            project=PROJECT,
            part=CORE_PART,
            operation=opno,
            window_start=window_start,
        ))))
    core_clocks = _clock_index(core_clockings)

    subring_clockings = []
    for opno in (600, 605, 608, 610, 612, 615):
        subring_clockings.extend(_rows(client.execute_query(SQL_CLOCKINGS.format(
            site=SITE,
            project=PROJECT,
            part=SUBRING_PART,
            operation=opno,
            window_start=window_start,
        ))))
    subring_clocks = _clock_index(subring_clockings)

    intervals: dict[str, list[dict]] = {
        "shell_lamination_mold": [],
        "trim_operation_clock_span": [],
        "assembly_fixture_subring": [],
        "assembly_fixture_shell_fit_candidate_op630": [],
        "electrical_seal_labor": [],
        "core_form_mold_set": [],
    }
    order_summaries = []
    for order in top_orders:
        so = str(order["SO"])
        ops = clocks.get(so, {})
        serial = serials.get(so)
        candidates = {
            "shell_lamination_mold": _interval(
                ops, acquire_ops=(50, 90, 130), release_op=570, release_boundary="start"
            ),
            "trim_operation_clock_span": _interval(ops, acquire_ops=(580,), release_op=580),
            "assembly_fixture_shell_fit_candidate_op630": _interval(
                ops, acquire_ops=(620,), release_op=630
            ),
            "electrical_seal_labor": _interval(ops, acquire_ops=(775,), release_op=775),
        }
        for name, interval in candidates.items():
            if interval:
                interval.update({"so": so, "serial": serial})
                intervals[name].append(interval)
        order_summaries.append({
            "so": so,
            "serial": serial,
            "state": order.get("STATE"),
            "closed": order.get("CLOSED"),
            "clocked_operations": sorted(ops),
            "intervals": {
                name: _serialize_interval(value) if value else None
                for name, value in candidates.items()
            },
        })

    subring_order_summaries = []
    for order in subring_orders:
        so = str(order["SO"])
        ops = subring_clocks.get(so, {})
        interval = _interval(
            ops, acquire_ops=(600,), release_op=612, release_boundary="start"
        )
        if interval:
            interval.update({"so": so, "serial": None})
            intervals["assembly_fixture_subring"].append(interval)
        subring_order_summaries.append({
            "so": so,
            "state": order.get("STATE"),
            "closed": order.get("CLOSED"),
            "routing_revision": order.get("REVISION"),
            "clocked_operations": sorted(ops),
            "interval": _serialize_interval(interval) if interval else None,
        })

    core_order_summaries = []
    for order in core_orders:
        so = str(order["SO"])
        ops = core_clocks.get(so, {})
        interval = _interval(ops, acquire_ops=(600,), release_op=700)
        if interval:
            interval.update({"so": so, "serial": None})
            intervals["core_form_mold_set"].append(interval)
        core_order_summaries.append({
            "so": so,
            "state": order.get("STATE"),
            "closed": order.get("CLOSED"),
            "routing_revision": order.get("REVISION"),
            "clocked_operations": sorted(ops),
            "interval": _serialize_interval(interval) if interval else None,
        })

    intervals["assembly_fixture_combined_candidate"] = [
        *intervals["assembly_fixture_subring"],
        *intervals["assembly_fixture_shell_fit_candidate_op630"],
    ]

    capacities = {
        "shell_lamination_mold": 3,
        "trim_operation_clock_span": 1,
        "assembly_fixture_subring": 2,
        "assembly_fixture_shell_fit_candidate_op630": 2,
        "assembly_fixture_combined_candidate": 2,
        "electrical_seal_labor": None,
        "core_form_mold_set": 1,
    }
    summaries = {
        name: _summarize_intervals(rows, capacities[name])
        for name, rows in intervals.items()
    }
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window_start": window_start,
        "scope": {"site": SITE, "project": PROJECT, "top_part": TOP_PART},
        "top_routing": {
            "selected_revision": routing["selected_revision"],
            "selected_alternative": routing["selected_alternative"],
            "active_order_count": routing["active_order_count"],
            "operations": routing["routing"],
        },
        "order_sample_limit": 100,
        "order_count": len(top_orders),
        "subring_order_count": len(subring_orders),
        "core_order_count": len(core_orders),
        "core_order_parts": sorted({str(row.get("PART_NO")) for row in core_orders}),
        "subring_routing": {
            "selected_revision": subring_routing["selected_revision"],
            "selected_alternative": subring_routing["selected_alternative"],
            "active_order_count": subring_routing["active_order_count"],
            "operations": subring_routing["routing"],
        },
        "subring_routing_search": _rows(client.execute_query(SQL_SUBRING_ROUTING_SEARCH.format(site=SITE))),
        "core_routing": {
            "selected_revision": core_routing["selected_revision"],
            "selected_alternative": core_routing["selected_alternative"],
            "active_order_count": core_routing["active_order_count"],
            "operations": core_routing["routing"],
        },
        "core_routing_rows": _rows(client.execute_query(SQL_CORE_ROUTING.format(
            site=SITE, part=CORE_PART
        ))),
        "interval_summaries": summaries,
        "orders": order_summaries,
        "subring_orders": subring_order_summaries,
        "core_orders": core_order_summaries,
        "limitations": [
            "Clocking boundaries are evidence of labor timing, not proof of physical tool release.",
            "Op 580 clocking covers both in-fixture trim and post-release chamfer work on a dolly; its clock span is not a trim-fixture occupancy interval.",
            "The op-630 assembly-fixture release is a candidate boundary only; the WI removes the drill basket but does not explicitly remove the radome from the assembly fixture.",
            "The shell-mold acquisition falls back from op 50 to op 90 or 130 only when earlier clocking is absent.",
        ],
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-start", default="2025-01-01")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        date.fromisoformat(args.window_start)
    except ValueError:
        parser.error("--window-start must use YYYY-MM-DD")
    try:
        result = await audit(args.window_start)
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
            print(args.output)
        else:
            print(payload)
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
