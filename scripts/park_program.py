"""Audit or park an unpublished program without deleting its history."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.database import async_session, engine  # noqa: E402
from app.engines import router_registry  # noqa: E402
from app.models import (  # noqa: E402
    ForecastLog,
    ModelEpoch,
    ObservationQuarantineEvent,
    PositionState,
    Program,
)
from app.services import model_epoch_service  # noqa: E402
from app.services import program_service  # noqa: E402


async def _snapshot(db, code: str) -> dict:
    program = await db.get(Program, code)
    if program is None:
        raise RuntimeError(f"Program {code} was not found")
    epochs = (await db.execute(
        select(ModelEpoch).where(ModelEpoch.program == code).order_by(ModelEpoch.id)
    )).scalars().all()
    states = []
    for epoch in epochs:
        transition = await model_epoch_service.current_transition(db, epoch.id)
        states.append({
            "id": epoch.id,
            "epoch_key": epoch.epoch_key,
            "state": transition.to_state,
        })
    published = await model_epoch_service.published_epoch(db, code)
    return {
        "program": code,
        "active": bool(program.active),
        "published_epoch": published.epoch.epoch_key if published else None,
        "epochs": states,
        "position_rows": int(await db.scalar(select(func.count(PositionState.id)).where(
            PositionState.program == code)) or 0),
        "forecast_log_rows": int(await db.scalar(select(func.count(ForecastLog.id)).where(
            ForecastLog.program == code)) or 0),
        "bcalay_quarantine_events": int(await db.scalar(select(
            func.count(ObservationQuarantineEvent.id)).where(
                ObservationQuarantineEvent.stream_key == "BCALAY")) or 0),
        "active_programs": program_service.program_order(),
        "registry_programs": sorted(router_registry.registry.programs),
    }


async def main(program: str, commit: bool) -> int:
    try:
        async with async_session() as db:
            code = program.strip().upper()
            before = await _snapshot(db, code)
            result = None
            if commit:
                result = await program_service.deactivate_program(
                    db, code,
                    actor="TwinWorks scope administration",
                    rationale=(
                        "Park BCA under the 2026-09-02 three-program product-scope decision; "
                        "retain immutable discovery, epoch, WIP, and quarantine history"
                    ),
                )
            after = await _snapshot(db, code)
            if commit:
                if after["active"]:
                    raise RuntimeError(f"Program {code} is still active")
                if any(item["state"] not in {"ARCHIVED", "DEPRECATED"}
                       for item in after["epochs"]):
                    raise RuntimeError(f"Program {code} has a nonterminal epoch after parking")
                for field in (
                    "position_rows", "forecast_log_rows", "bcalay_quarantine_events",
                ):
                    if after[field] != before[field]:
                        raise RuntimeError(f"Parking changed retained history field {field}")
            print(json.dumps({
                "mode": "COMMIT" if commit else "DRY_RUN",
                "before": before,
                "result": result,
                "after": after,
            }, indent=2, sort_keys=True))
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", default="BCAFIN")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.program, args.commit)))
