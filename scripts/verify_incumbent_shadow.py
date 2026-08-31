"""Create and verify incumbent DB-shadow epochs against the published legacy model."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session, engine  # noqa: E402
from app.services.model_epoch_service import verify_incumbent_shadow_parity  # noqa: E402


async def _run(commit: bool) -> int:
    try:
        async with async_session() as db:
            report = await verify_incumbent_shadow_parity(db)
            payload = {
                "exact_match": report.exact_match,
                "programs": list(report.programs),
                "unit_counts": report.unit_counts,
                "candidate_epoch_ids": report.candidate_epoch_ids,
                "legacy_snapshot_id": report.legacy_snapshot_id,
                "shadow_snapshot_id": report.shadow_snapshot_id,
                "legacy_result_hash": report.legacy_result_hash,
                "shadow_result_hash": report.shadow_result_hash,
                "mismatched_serials": list(report.mismatched_serials),
                "open_review_debt": report.open_review_debt,
                "review_debt_by_type": report.review_debt_by_type,
                "committed": bool(commit and report.exact_match),
            }
            if commit and report.exact_match:
                await db.commit()
            else:
                await db.rollback()
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if report.exact_match else 1
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commit", action="store_true",
        help="Persist OBSERVE candidates, replay snapshots, and review debt after exact parity",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.commit))


if __name__ == "__main__":
    raise SystemExit(main())
