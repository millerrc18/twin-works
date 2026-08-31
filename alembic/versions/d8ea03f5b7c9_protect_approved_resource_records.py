"""protect approved resource governance records

Revision ID: d8ea03f5b7c9
Revises: c7d9e2f4a6b8
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op

from app.models import APPROVED_ASSUMPTION_TRIGGER, APPROVED_CAPACITY_TRIGGER


revision: str = "d8ea03f5b7c9"
down_revision: Union[str, Sequence[str], None] = "c7d9e2f4a6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(APPROVED_ASSUMPTION_TRIGGER)
    op.execute(APPROVED_CAPACITY_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_resource_capacity_approved_immutable")
    op.execute("DROP TRIGGER IF EXISTS trg_model_assumption_approved_immutable")
