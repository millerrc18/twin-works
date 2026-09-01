"""Persist the current BCA layup state conflicts into the local append-only quarantine."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session, engine  # noqa: E402
from app.services.observation_quarantine import reconcile_quarantines  # noqa: E402
from scripts.audit_bca_layup import PART, PROJECT, audit  # noqa: E402


STREAM = "BCALAY"
REASON = "TERMINAL_COMPLETE_STATE_OPEN"
ACTOR = "TwinWorks BCA layup state audit"


async def main() -> int:
    try:
        report = await audit()
        async with async_session() as db:
            result = await reconcile_quarantines(
                db, stream_key=STREAM, project_id=PROJECT, part_no=PART,
                reason_code=REASON, conflicts=report["quarantine_orders"], actor=ACTOR,
            )
            await db.commit()
            output = {
                "stream_key": STREAM,
                "opened": result.opened,
                "reopened": result.reopened,
                "resolved": result.resolved,
                "active_quarantine_count": len(result.active),
                "active_orders": [
                    {"so": row.order_no, "serial": row.serial, "event_key": row.event_key}
                    for row in result.active
                ],
                "eligible_order_count": len(report["eligible_orders"]),
                "eligible_bca_load": report["eligible_bca_load"],
            }
            print(json.dumps(output, indent=2, sort_keys=True))
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
