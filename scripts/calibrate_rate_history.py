"""Run read-only IFS RATE-01c labor/throughput calibration for Elevator and Aeronose."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data import token_store  # noqa: E402
from app.data.ifs_mcp_client import IfsMcpClient  # noqa: E402
from app.database import async_session, engine  # noqa: E402
from app.engines.router_registry import registry  # noqa: E402
from app.engines.rtg_wrapper import run_pooled  # noqa: E402
from app.services import program_service  # noqa: E402
from app.services.rate_calibration import (  # noqa: E402
    CalibrationThresholds,
    build_monthly_periods,
    calibrate_program,
    rollup_work_center_labor,
)
from app.services.rate_calibration_ifs import (  # noqa: E402
    _rows,
    parse_history_rows,
    query_program_history,
    work_center_labor_observations,
    work_center_labor_sql,
)
from app.services.rate_governance import build_rate_baseline_context  # noqa: E402
from app.services.resource_profile import compile_profile  # noqa: E402


PROGRAMS = ("ELEV", "RAD")
PACK_OPS = {"ELEV": 4200, "RAD": 790}


def _work_center_labor_payload(rows):
    rollups = rollup_work_center_labor(rows)
    return {
        work_center: rollup
        for (_program, work_center), rollup in rollups.items()
    }


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_timestamp(value) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


async def main(args) -> int:
    history_start = _parse_date(args.history_start)
    measurement_start = _parse_date(args.measurement_start)
    measurement_end = _parse_date(args.measurement_end)
    if not history_start <= measurement_start <= measurement_end:
        raise ValueError("history_start <= measurement_start <= measurement_end is required")

    async with async_session() as db:
        tokens = await token_store.load_tokens(db, "ifs")
    if not tokens:
        raise RuntimeError("Connect TwinWorks to IFS before calibration")
    client = IfsMcpClient(**tokens)

    specs = program_service.ifs_meta()
    raw_history = {}
    for program in PROGRAMS:
        project, parts = specs[program]
        history = await asyncio.to_thread(
            query_program_history,
            client,
            project=project,
            parts=tuple(parts),
            pack_op=PACK_OPS[program],
            window_start=history_start,
            window_end=measurement_end,
        )
        raw_history[program] = history
    all_rows = [row for rows in raw_history.values() for row in rows]
    if not all_rows:
        raise RuntimeError("IFS returned no current-part history rows")
    actual_starts = [
        _parse_timestamp(row.get("ACTUAL_START")) for row in all_rows
        if row.get("ACTUAL_START")
    ]
    as_of = min(actual_starts)
    horizon_end = measurement_end + timedelta(days=365)

    async with async_session() as db:
        context = await build_rate_baseline_context(
            db,
            programs=list(PROGRAMS),
            baseline_kind="PUBLISHED",
            as_of=as_of,
            horizon_end=horizon_end,
        )
        compiled = await compile_profile(
            db,
            programs=list(PROGRAMS),
            as_of=as_of,
            horizon_end=horizon_end,
            mode="LEGACY",
            epoch_ids={program: ref.epoch_id for program, ref in context.epochs.items()},
        )
        await db.commit()

    units_by_program = {program: [] for program in PROGRAMS}
    model_hours = {
        program: Decimal(str(sum(float(row[3]) for row in registry.ops(program))))
        for program in PROGRAMS
    }
    for program, rows in raw_history.items():
        for row in rows:
            start = _parse_timestamp(row["ACTUAL_START"])
            due = date.fromisoformat(row["DUE_DATE"]) if row.get("DUE_DATE") else None
            row["MODEL_LABOR_HOURS"] = model_hours[program]
            units_by_program[program].append({
                "serial": str(row["ORDER_NO"]),
                "so": str(row["ORDER_NO"]),
                "maxop": 0,
                "commit": due,
                "program": program,
                "release_at": start,
                "scenario_only": True,
            })
    simulated = run_pooled(
        units_by_program, as_of,
        profile=compiled.scheduler_profile,
        trace_constraints=False,
    )
    modeled_finishes = {
        order_no: payload["finish"] for order_no, payload in simulated.items()
        if payload.get("finish")
    }

    thresholds = CalibrationThresholds(
        minimum_orders=args.minimum_orders,
        cycle_mae_days_max=Decimal(str(args.cycle_mae_days)),
        completion_wape_max=Decimal(str(args.completion_wape)),
        wip_wape_max=Decimal(str(args.wip_wape)),
        labor_wape_max=Decimal(str(args.labor_wape)),
    )
    output = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(),
        "history_start": history_start,
        "measurement_start": measurement_start,
        "measurement_end": measurement_end,
        "baseline": context,
        "thresholds": thresholds,
        "threshold_status": "DIAGNOSTIC_UNAPPROVED",
        "tooling_readiness": "UNRESOLVED",
        "staffing_readiness": "UNRESOLVED",
        "programs": {},
        "caveats": [
            "Actual start is the first IFS labor clock on the top-level shop order.",
            "Actual completion is the latest finish clock on the closed configured terminal operation.",
            "Modeled labor uses the current TwinWorks route; IFS historical plan is diagnostic only.",
            "The cohort is limited to current configured top-level parts and a finite warm-up window.",
            "Diagnostic thresholds are not owner-approved and cannot open RATE-01d.",
            "Staffing denominators, learning/retention evidence, and tooling remain unresolved.",
        ],
    }
    for program in PROGRAMS:
        orders, flows = parse_history_rows(
            program, raw_history[program], modeled_finishes=modeled_finishes)
        measurement_orders = tuple(
            order for order in orders
            if measurement_start <= order.actual_completion.date() <= measurement_end)
        measurement_flows = tuple(
            row for row in flows
            if row.actual_start.date() <= measurement_end
            and (row.actual_completion is None
                 or row.actual_completion.date() >= measurement_start))
        periods = build_monthly_periods(
            orders=measurement_orders,
            flow_units=measurement_flows,
            measurement_start=measurement_start,
            measurement_end=measurement_end,
        )
        report = calibrate_program(
            program=program,
            orders=measurement_orders,
            periods=periods,
            thresholds=thresholds,
            staffing_readiness="UNRESOLVED",
            tooling_readiness="UNRESOLVED",
            thresholds_approved=False,
        )
        completed_ids = tuple(order.order_no for order in measurement_orders)
        wc_rows = (_rows(await asyncio.to_thread(
            client.execute_query,
            work_center_labor_sql(completed_ids, cutoff=measurement_end)))
                   if completed_ids else [])
        wc_observations = work_center_labor_observations(
            program=program,
            completed_orders=len(measurement_orders),
            route_ops=list(registry.ops(program)),
            actual_rows=wc_rows,
        )
        output["programs"][program] = {
            "report": report,
            "periods": periods,
            "orders": measurement_orders,
            "flow_unit_count": len(measurement_flows),
            "work_center_labor": _work_center_labor_payload(wc_observations),
            "ifs_planned_labor_hours": {
                str(row["ORDER_NO"]): str(row.get("IFS_PLANNED_LABOR_HOURS") or 0)
                for row in raw_history[program]
                if str(row["ORDER_NO"]) in completed_ids
            },
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    for program in PROGRAMS:
        report = output["programs"][program]["report"]
        print(
            f"{program}: n={report.metrics.sample_orders} "
            f"cycle_MAE={report.metrics.cycle_mae_days}d "
            f"completion_WAPE={report.metrics.completion_wape} "
            f"WIP_WAPE={report.metrics.wip_wape} "
            f"labor_WAPE={report.metrics.labor_wape} "
            f"status={report.labor_calibration_status}"
        )
    await engine.dispose()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-start", default="2025-12-01")
    parser.add_argument("--measurement-start", default="2026-03-01")
    parser.add_argument("--measurement-end", default="2026-09-17")
    parser.add_argument("--minimum-orders", type=int, default=8)
    parser.add_argument("--cycle-mae-days", type=float, default=14.0)
    parser.add_argument("--completion-wape", type=float, default=0.25)
    parser.add_argument("--wip-wape", type=float, default=0.25)
    parser.add_argument("--labor-wape", type=float, default=0.25)
    parser.add_argument(
        "--output", type=Path,
        default=Path("output/rate_calibration_2026-09-17.json"))
    raise SystemExit(asyncio.run(main(parser.parse_args())))
