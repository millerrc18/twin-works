"""Revision-aware IFS routing discovery for program onboarding.

Discovery is read-only. It selects a manufacturing routing revision from active shop-order usage,
preserves operation economics in the review draft, and classifies non-production rows before the
unknown-work-center gate runs.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


SQL_ACTIVE_REVISIONS = """
SELECT s.ROUTING_REVISION AS REVISION, s.ROUTING_ALTERNATIVE AS ALTERNATIVE,
       COUNT(*) AS ORDER_COUNT, MIN(s.ORDER_NO) AS SAMPLE_ORDER
FROM SHOP_ORD_CFV s
WHERE s.CONTRACT = '{site}' AND s.PROJECT_ID = '{project}' AND s.PART_NO = '{part}'
  AND s.CLOSE_DATE IS NULL
GROUP BY s.ROUTING_REVISION, s.ROUTING_ALTERNATIVE
ORDER BY s.ROUTING_REVISION, s.ROUTING_ALTERNATIVE
"""

SQL_ROUTING_REVISIONS = """
SELECT r.ROUTING_REVISION AS REVISION, r.ALTERNATIVE_NO AS ALTERNATIVE,
       COUNT(*) AS OP_COUNT,
       ROUND(SUM(NVL(r.LABOR_SETUP_TIME,0)+NVL(r.LABOR_RUN_FACTOR,0)),3) AS LABOR_HOURS,
       ROUND(SUM(NVL(r.MACH_SETUP_TIME,0)+NVL(r.MACH_RUN_FACTOR,0)),3) AS MACHINE_HOURS
FROM ROUTING_OPERATION_CFV r
WHERE r.CONTRACT = '{site}' AND r.PART_NO = '{part}' AND r.BOM_TYPE_DB = 'M'
GROUP BY r.ROUTING_REVISION, r.ALTERNATIVE_NO
ORDER BY r.ROUTING_REVISION, r.ALTERNATIVE_NO
"""

SQL_ROUTING = """
SELECT r.OPERATION_NO AS OPNO, r.WORK_CENTER_NO AS WC,
       r.OPERATION_DESCRIPTION AS DESCR, r.ROUTING_REVISION AS REVISION,
       r.ALTERNATIVE_NO AS ALTERNATIVE, r.LABOR_SETUP_TIME AS LABOR_SETUP,
       r.LABOR_RUN_FACTOR AS LABOR_RUN, r.MACH_SETUP_TIME AS MACHINE_SETUP,
       r.MACH_RUN_FACTOR AS MACHINE_RUN, r.CREW_SIZE AS CREW_SIZE,
       r.SETUP_CREW_SIZE AS SETUP_CREW_SIZE, r.RUN_TIME_CODE_DB AS RUN_TIME_CODE,
       r.PARALLEL_OPERATION_DB AS PARALLEL, r.PHASE_IN_DATE AS PHASE_IN,
       r.PHASE_OUT_DATE AS PHASE_OUT, r.NOTE_TEXT AS NOTE_TEXT
FROM ROUTING_OPERATION_CFV r
WHERE r.CONTRACT = '{site}' AND r.PART_NO = '{part}' AND r.BOM_TYPE_DB = 'M'
  AND r.ROUTING_REVISION = '{revision}' AND r.ALTERNATIVE_NO = '{alternative}'
ORDER BY r.OPERATION_NO
"""

SQL_REFERENCE_STATUS = """
SELECT o.OPERATION_NO AS OPNO, o.OPER_STATUS_CODE_DB AS STATUS_CODE,
       o.OPERATION_SCHED_STATUS_DB AS SCHED_STATUS
FROM SO_OPER_DISPATCH_LIST_CFV o
WHERE o.ORDER_NO = '{order_no}'
ORDER BY o.OPERATION_NO
"""


class RoutingRevisionRequired(ValueError):
    """Raised when no single routing revision can be selected safely."""

    def __init__(self, revisions: list[dict], active_counts: dict[str, int]):
        super().__init__("Select a routing revision")
        self.revisions = revisions
        self.active_counts = active_counts


def _literal(value: Any) -> str:
    return str(value or "").strip().replace("'", "''")


def _rows(result) -> list[dict]:
    return result.get("data", []) if isinstance(result, dict) else (result or [])


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _revision_key(value: str):
    text = str(value or "")
    try:
        return (0, int(text))
    except ValueError:
        return (1, text)


def _revision_options(master_rows: list[dict], active_rows: list[dict]) -> list[dict]:
    active_counts = defaultdict(int)
    sample_orders = {}
    for row in active_rows:
        pair = (str(row.get("REVISION") or ""), str(row.get("ALTERNATIVE") or "*"))
        active_counts[pair] += int(row.get("ORDER_COUNT") or 0)
        if row.get("SAMPLE_ORDER"):
            sample_orders.setdefault(pair, str(row["SAMPLE_ORDER"]))
    grouped: dict[tuple[str, str], dict] = {}
    for row in master_rows:
        revision = str(row.get("REVISION") or "")
        alternative = str(row.get("ALTERNATIVE") or "*")
        pair = (revision, alternative)
        item = grouped.setdefault(pair, {
            "revision": revision, "alternative": alternative, "op_count": 0,
            "labor_hours": 0.0, "machine_hours": 0.0,
        })
        item["op_count"] += int(row.get("OP_COUNT") or 0)
        item["labor_hours"] += _number(row.get("LABOR_HOURS"))
        item["machine_hours"] += _number(row.get("MACHINE_HOURS"))
    options = []
    for pair, item in grouped.items():
        item["labor_hours"] = round(item["labor_hours"], 3)
        item["machine_hours"] = round(item["machine_hours"], 3)
        item["active_order_count"] = active_counts.get(pair, 0)
        item["reference_order"] = sample_orders.get(pair)
        options.append(item)
    return sorted(options, key=lambda item: (_revision_key(item["revision"]), item["alternative"]))


def _select_routing(options: list[dict], requested_revision: str | None,
                    requested_alternative: str | None) -> dict:
    revision = str(requested_revision or "").strip()
    alternative = str(requested_alternative or "").strip()
    candidates = options
    if revision:
        candidates = [item for item in options if item["revision"] == revision]
        if not candidates:
            raise ValueError(f"Routing revision {revision} is not available")
        if alternative:
            candidates = [item for item in candidates if item["alternative"] == alternative]
            if not candidates:
                raise ValueError(f"Routing revision {revision} alternative {alternative} is not available")
    active = [item for item in candidates if item["active_order_count"] > 0]
    ranked = active or candidates
    if ranked:
        peak = max(item["active_order_count"] for item in ranked)
        winners = [item for item in ranked if item["active_order_count"] == peak]
        if len(winners) == 1:
            return winners[0]
    counts = {
        f"{item['revision']}/{item['alternative']}": item["active_order_count"]
        for item in options if item["active_order_count"] > 0
    }
    raise RoutingRevisionRequired(options, counts)


def _classification(opno: int, wc: str, description: str) -> str:
    upper_wc = wc.upper()
    upper_desc = description.upper()
    if opno >= 9999 or upper_desc == "TO STOCK":
        return "terminal"
    if upper_wc.startswith("WAIT") or upper_desc.startswith("WAITING ON"):
        return "waiting"
    if ((opno in {1, 2, 9}) and
            any(term in upper_desc for term in ("EFFECTIVE DOCUMENT", "CHANGE LOG", "GENERAL INSPECTION"))):
        return "administrative"
    return "production"


def known_wcs() -> set:
    """Work centers with an explicit capacity budget in the current scheduler profile."""
    import routers as R
    return {wc for (_program, wc) in R.WC_SHIFT.keys()}


def discover_routing(client, *, project_id: str, part_no: str,
                     revision: str | None = None, alternative: str | None = None,
                     site: str = "59") -> dict:
    """Return one reviewed routing revision and its full onboarding economics."""
    values = {"site": _literal(site), "project": _literal(project_id),
              "part": _literal(part_no)}
    active_rows = _rows(client.execute_query(SQL_ACTIVE_REVISIONS.format(**values)))
    master_rows = _rows(client.execute_query(SQL_ROUTING_REVISIONS.format(**values)))
    options = _revision_options(master_rows, active_rows)
    if not options:
        raise ValueError(f"No manufacturing routing found for {part_no}")
    selected_option = _select_routing(options, revision, alternative)
    selected = selected_option["revision"]
    alternative = selected_option["alternative"]
    active_count = selected_option["active_order_count"]
    reference_order = selected_option["reference_order"]
    route_rows = _rows(client.execute_query(SQL_ROUTING.format(
        **values, revision=_literal(selected), alternative=_literal(alternative))))
    status_by_op = {}
    if reference_order:
        status_rows = _rows(client.execute_query(SQL_REFERENCE_STATUS.format(
            order_no=_literal(reference_order))))
        status_by_op = {int(row["OPNO"]): row for row in status_rows if row.get("OPNO") is not None}

    routing = []
    for row in route_rows:
        try:
            opno = int(row["OPNO"])
        except (TypeError, ValueError):
            continue
        wc = str(row.get("WC") or "").strip()
        description = str(row.get("DESCR") or "").strip()
        classification = _classification(opno, wc, description)
        status = status_by_op.get(opno, {})
        labor_setup = _number(row.get("LABOR_SETUP"))
        labor_run = _number(row.get("LABOR_RUN"))
        machine_setup = _number(row.get("MACHINE_SETUP"))
        machine_run = _number(row.get("MACHINE_RUN"))
        routing.append({
            "opno": opno, "wc": wc, "desc": description,
            "revision": selected, "alternative": alternative,
            "labor_setup_hours": labor_setup, "labor_run_hours": labor_run,
            "labor_hours": round(labor_setup + labor_run, 5),
            "machine_setup_hours": machine_setup, "machine_run_hours": machine_run,
            "machine_hours": round(machine_setup + machine_run, 5),
            "crew_size": _number(row.get("CREW_SIZE")) or 1.0,
            "setup_crew_size": _number(row.get("SETUP_CREW_SIZE")) or None,
            "run_time_code": row.get("RUN_TIME_CODE"),
            "parallel": str(row.get("PARALLEL") or "N").upper() not in {"N", "FALSE", "0"},
            "phase_in": row.get("PHASE_IN"), "phase_out": row.get("PHASE_OUT"),
            "note_text": row.get("NOTE_TEXT"),
            "status_code": status.get("STATUS_CODE"),
            "schedule_status": status.get("SCHED_STATUS"),
            "status_reference_order": reference_order,
            "nowb": "(NOWB)" in description.upper(),
            "classification": classification,
            "included": classification == "production",
        })
    all_labor = round(sum(op["labor_hours"] for op in routing), 3)
    all_machine = round(sum(op["machine_hours"] for op in routing), 3)
    included = [op for op in routing if op["included"]]
    return {
        "project_id": str(project_id), "part_no": str(part_no), "site": str(site),
        "selected_revision": selected, "selected_alternative": alternative,
        "active_order_count": active_count, "reference_order": reference_order,
        "revisions": options, "routing": routing,
        "totals": {
            "all_labor_hours": all_labor,
            "all_machine_hours": all_machine,
            "included_labor_hours": round(sum(op["labor_hours"] for op in included), 1),
            "included_machine_hours": round(sum(op["machine_hours"] for op in included), 1),
            "included_operations": len(included),
            "excluded_operations": len(routing) - len(included),
        },
    }


def unknown_wcs(routing: list[dict]) -> list[str]:
    """Included production WCs with no explicit budget; excluded rows do not block save."""
    known = known_wcs()
    seen, unknown = set(), []
    for op in routing:
        if op.get("included") is False:
            continue
        wc = op.get("wc")
        if wc and wc not in known and wc not in seen:
            seen.add(wc)
            unknown.append(wc)
    return unknown
