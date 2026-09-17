"""Create and compare governed Aeronose op-775 cure successors."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.snapshot_source import SnapshotDataSource  # noqa: E402
from app.database import async_session, engine  # noqa: E402
from app.services.aeronose_cure_candidate import (  # noqa: E402
    compare_cure_successor,
    ensure_cure_successors,
)
from app.services.model_epoch_service import (  # noqa: E402
    current_transition,
    published_epoch,
)


async def main(commit: bool) -> int:
    async with async_session() as db:
        candidates = await ensure_cure_successors(
            db, actor="Ryan Miller", drdi={"status": "PENDING"})
        ds = SnapshotDataSource()
        units = {
            "RAD": [unit.as_sim_unit() for unit in ds.get_wip_units("RAD") if not unit.stalled]
        }
        horizon = max(
            (row["commit"] for row in units["RAD"] if row.get("commit")),
            default=ds.as_of().date(),
        )
        comparison = await compare_cure_successor(
            db,
            epoch_id=candidates.no_station_epoch_id,
            units_by_program=units,
            as_of=ds.as_of(),
            horizon_end=horizon,
        )
        published = await published_epoch(db, "RAD")
        result = {
            "mode": "COMMIT" if commit else "ROLLBACK",
            "published_epoch": published.epoch.epoch_key if published else None,
            "no_station": {
                "epoch_id": candidates.no_station_epoch_id,
                "state": (await current_transition(
                    db, candidates.no_station_epoch_id)).to_state,
            },
            "accelerated_drdi": {
                "epoch_id": candidates.accelerated_epoch_id,
                "state": (await current_transition(
                    db, candidates.accelerated_epoch_id)).to_state,
                "approval_status": "PENDING",
            },
            "comparison": {
                "changed_units": comparison.changed_units,
                "baseline_snapshot_id": comparison.baseline_snapshot_id,
                "candidate_snapshot_id": comparison.candidate_snapshot_id,
                "replay_exact": comparison.replay_exact,
                "units": [
                    {
                        "serial": row.serial,
                        "baseline_finish": row.baseline_finish.isoformat(),
                        "candidate_finish": row.candidate_finish.isoformat(),
                        "delta_hours": row.delta_hours,
                    }
                    for row in comparison.units
                ],
            },
        }
        if commit:
            await db.commit()
        else:
            await db.rollback()
        print(json.dumps(result, indent=2, sort_keys=True))
    await engine.dispose()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    raise SystemExit(asyncio.run(main(parser.parse_args().commit)))
