"""Register project 521938 finishing in OBSERVE and materialize its live WIP."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.data import ifs_routing  # noqa: E402
from app.data import token_store  # noqa: E402
from app.database import async_session, engine  # noqa: E402
from app.engines import router_registry  # noqa: E402
from app.models import ForecastLog, PositionState, Program  # noqa: E402
from app.services import model_epoch_service  # noqa: E402
from app.services import planning_basis_service  # noqa: E402
from app.services import position_state  # noqa: E402
from app.services import program_service  # noqa: E402
from app.services import resource_explain  # noqa: E402
from app.services import sync_service  # noqa: E402


PROGRAM = "BCAFIN"
PROJECT = "521938"
PARTS = ("3301ED0031-101A", "3301ED0031-101C")
REVISION = "3"
ALTERNATIVE = "*"


def _canonical_json(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )


def _included(result) -> list[dict]:
    return [row for row in result["routing"] if row["included"]]


def _route_signature(result) -> list[list]:
    return [
        [row["opno"], row["desc"], row["wc"], row["labor_hours"], row["crew_size"]]
        for row in _included(result)
    ]


def _evidence(result) -> dict:
    routing = [
        {
            key: row[key]
            for key in (
                "opno", "wc", "desc", "labor_setup_hours", "labor_run_hours",
                "labor_hours", "machine_setup_hours", "machine_run_hours",
                "machine_hours", "crew_size", "run_time_code", "parallel",
                "classification", "included",
            )
        }
        for row in result["routing"]
    ]
    return {
        "part_no": result["part_no"],
        "site": result["site"],
        "routing_revision": result["selected_revision"],
        "routing_alternative": result["selected_alternative"],
        "active_order_count": result["active_order_count"],
        "reference_order": result["reference_order"],
        "totals": result["totals"],
        "unknown_work_centers": ifs_routing.unknown_wcs(result["routing"]),
        "routing": routing,
        "routing_hash": hashlib.sha256(_canonical_json(routing).encode("utf-8")).hexdigest(),
    }


async def main() -> int:
    try:
        async with async_session() as db:
            tokens = await token_store.load_tokens(db, "ifs")
            if not tokens:
                raise RuntimeError("Connect IFS before registering BCA")
            client = sync_service.IfsMcpClient(**tokens)
            discovered = {}
            for part in PARTS:
                discovered[part] = await asyncio.to_thread(
                    ifs_routing.discover_routing, client,
                    project_id=PROJECT, part_no=part,
                    revision=REVISION, alternative=ALTERNATIVE,
                )
            if any(result["selected_revision"] != REVISION for result in discovered.values()):
                raise RuntimeError("BCA discovery did not resolve revision 3")
            if _route_signature(discovered[PARTS[0]]) != _route_signature(discovered[PARTS[1]]):
                raise RuntimeError("BCA A/C labor routes no longer match")
            unknown = sorted({
                wc for result in discovered.values()
                for wc in ifs_routing.unknown_wcs(result["routing"])
            })
            if unknown != ["P3NDI", "P3TRI", "PRNG", "TRI A"]:
                raise RuntimeError(f"Unexpected BCA unknown work centers: {unknown}")

            published_before = {
                code: (await model_epoch_service.published_epoch(db, code)).epoch.epoch_key
                for code in ("ELEV", "RAD", "AEGIS")
            }
            source_metadata = {
                "schema_version": 1,
                "purpose": "observation_only_registration",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "project_id": PROJECT,
                "parts": [_evidence(discovered[part]) for part in PARTS],
                "shared_labor_route": True,
                "machine_time_decision": "UNRESOLVED_BCA_04",
                "capacity_status": "UNRESOLVED_BCA_03",
            }
            a_route = _included(discovered[PARTS[0]])
            operations = [
                [row["opno"], row["desc"], row["wc"], row["labor_hours"], "FIN"]
                for row in a_route
            ]
            existing = await db.get(Program, PROGRAM)
            if existing is None:
                created = await program_service.create_program(
                    db, code=PROGRAM, name="BCA Triband Finishing", plant="Plant 3",
                    project_id=PROJECT, part_nos=list(PARTS), ops=operations,
                    milestones=[["FIN", "Finishing"]], ceilings=[["FIN", 7000]],
                    pack_op=7000, ship_op=7000, floor_op=3000,
                    configured_planning_basis="CONTRACT_DATES", plan_label="Contract",
                    plan_version="IFS live 2026-08-31", epoch_metadata=source_metadata,
                    created_by="TwinWorks BCA observation registration",
                )
                epoch_id = created["epoch_id"]
            else:
                if existing.project_id != PROJECT:
                    raise RuntimeError("BCAFIN already exists with another project")
                latest = await model_epoch_service.latest_epoch(db, PROGRAM)
                epoch_id = latest.epoch.id

            transition = await model_epoch_service.current_transition(db, epoch_id)
            if transition.to_state == "DRAFT":
                transition = await model_epoch_service.transition_epoch(
                    db, epoch_id, to_state="OBSERVE",
                    actor="TwinWorks BCA observation registration",
                    authority_role="DATA_ADMIN",
                    rationale="Collect BCA finishing WIP and resource evidence without publishing dates",
                    evidence={
                        "project_id": PROJECT,
                        "parts": list(PARTS),
                        "routing_revision": REVISION,
                        "unknown_work_centers": unknown,
                        "publication_change": False,
                    },
                )
                await db.commit()

            program_service.invalidate_cache()
            router_registry.rebuild()
            pulled = await asyncio.to_thread(sync_service._pull_program, client, PROGRAM)
            unknown_serials = []
            for so, data in pulled.items():
                if data["serial"] == so:
                    unknown_serials.append(so)
                await position_state.upsert(
                    db, so, PROGRAM, data["serial"], maxop=data["maxop"],
                    last_clock=sync_service._pd(data["last_clock"]),
                    due=sync_service._pd(data["due"]),
                    closed=sync_service._pd(data["closed"]), source="ifs-sync",
                )
            await db.commit()
            position_state.invalidate_cache()

            planning = await planning_basis_service.context_for_program(db, PROGRAM)
            readiness = await resource_explain.program_readiness(
                db, PROGRAM, datetime.now().date())
            published_after = {
                code: (await model_epoch_service.published_epoch(db, code)).epoch.epoch_key
                for code in ("ELEV", "RAD", "AEGIS")
            }
            if published_before != published_after:
                raise RuntimeError("Incumbent publication changed during BCA registration")
            if await model_epoch_service.published_epoch(db, PROGRAM) is not None:
                raise RuntimeError("BCA observation candidate was published")
            forecast_rows = await db.scalar(select(func.count(ForecastLog.id)).where(
                ForecastLog.program == PROGRAM))
            position_rows = await db.scalar(select(func.count(PositionState.id)).where(
                PositionState.program == PROGRAM,
                PositionState.closed.is_(None),
            ))
            output = {
                "program": PROGRAM,
                "lifecycle": planning.lifecycle_state,
                "planning_basis": planning.configured_planning_basis,
                "basis_effective": planning.basis_effective,
                "forecast_visibility": planning.forecast_visibility,
                "published": False,
                "active_wip": position_rows,
                "unknown_serials": unknown_serials,
                "forecast_log_rows": forecast_rows,
                "resource_readiness": readiness["readiness"],
                "resource_issues": readiness["issues"],
                "published_incumbents": published_after,
                "discovery": {
                    part: {
                        "active_orders": discovered[part]["active_order_count"],
                        "rows": len(discovered[part]["routing"]),
                        "included": discovered[part]["totals"]["included_operations"],
                        "labor_hours": discovered[part]["totals"]["all_labor_hours"],
                        "machine_hours": discovered[part]["totals"]["all_machine_hours"],
                    }
                    for part in PARTS
                },
            }
            print(json.dumps(output, indent=2, sort_keys=True))
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
