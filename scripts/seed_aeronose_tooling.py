"""Audit or seed the internal-only Aeronose tooling inventory."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session, engine  # noqa: E402
from app.services.tooling_seed import (  # noqa: E402
    aeronose_tooling_inventory,
    seed_aeronose_tooling_drafts,
)


async def main(commit: bool) -> int:
    try:
        async with async_session() as db:
            before = await aeronose_tooling_inventory(db)
            result = None
            if commit:
                result = await seed_aeronose_tooling_drafts(db)
                await db.commit()
            after = await aeronose_tooling_inventory(db)
            if commit:
                for row in after:
                    if (not row["present"] or row["slot_count"] != row["expected_count"]
                            or row["capacity_status"] != "DRAFT"
                            or row["assumption_status"] != "DRAFT"
                            or row["commitment_grade"] != "INTERNAL_ONLY"
                            or row["binding_count"] != 0):
                        raise RuntimeError(f"Invalid Aeronose tooling draft: {row}")
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
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.commit)))
