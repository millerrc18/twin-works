"""harden assumption review type and resolution coherence

Revision ID: dbe1f2a3b4c5
Revises: cad0e1f2a3b4
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op

from app.models import (
    ASSUMPTION_REVIEW_DELETE_TRIGGER,
    ASSUMPTION_REVIEW_RESOLUTION_TRIGGER,
)


revision: str = "dbe1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "cad0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_assumption_review_resolution_immutable")
    op.execute("DROP TRIGGER IF EXISTS trg_assumption_review_delete_immutable")


def upgrade() -> None:
    _drop_triggers()
    with op.batch_alter_table("assumption_review") as batch_op:
        batch_op.drop_constraint("ck_assumption_review_resolution", type_="check")
        batch_op.drop_constraint("ck_assumption_review_type", type_="check")
        batch_op.create_check_constraint(
            "ck_assumption_review_type",
            "review_type IN ('EXPIRY','MISSING_REVIEW_DATE','MISSING_DRIFT_POLICY',"
            "'BACKFILL_ATTESTATION','DRIFT','SPARSE_EVIDENCE','MANUAL')",
        )
        batch_op.create_check_constraint(
            "ck_assumption_review_resolution",
            "(status = 'OPEN' AND resolution IS NULL AND successor_assumption_id IS NULL) OR "
            "(status = 'DISMISSED' AND resolution = 'DISMISSED' "
            "AND successor_assumption_id IS NULL) OR "
            "(status = 'RESOLVED' AND resolution IN ('RECERTIFIED','SUPERSEDED') "
            "AND successor_assumption_id IS NOT NULL)",
        )
    op.execute(ASSUMPTION_REVIEW_RESOLUTION_TRIGGER)
    op.execute(ASSUMPTION_REVIEW_DELETE_TRIGGER)


def downgrade() -> None:
    _drop_triggers()
    with op.batch_alter_table("assumption_review") as batch_op:
        batch_op.drop_constraint("ck_assumption_review_resolution", type_="check")
        batch_op.drop_constraint("ck_assumption_review_type", type_="check")
        batch_op.create_check_constraint(
            "ck_assumption_review_type",
            "review_type IN ('EXPIRY','MISSING_REVIEW_DATE','DRIFT',"
            "'SPARSE_EVIDENCE','MANUAL')",
        )
        batch_op.create_check_constraint(
            "ck_assumption_review_resolution",
            "resolution IS NULL OR resolution IN "
            "('RECERTIFIED','SUPERSEDED','DISMISSED')",
        )
    op.execute(ASSUMPTION_REVIEW_RESOLUTION_TRIGGER)
    op.execute(ASSUMPTION_REVIEW_DELETE_TRIGGER)
