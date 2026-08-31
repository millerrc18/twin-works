"""ensure slot assignment schema exists on clean Alembic installs

Revision ID: a8c3d4e5f6a7
Revises: f7b2c3d4e5f6
Create Date: 2026-08-28
"""
from typing import Sequence, Union
import logging

from alembic import op
import sqlalchemy as sa


revision: str = "a8c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "f7b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "slot_assignment" in set(inspector.get_table_names()):
        required = {
            "id", "slot_id", "program", "hand", "target_date", "serial", "updated_at",
        }
        actual = {column["name"] for column in inspector.get_columns("slot_assignment")}
        if not required <= actual:
            raise RuntimeError(
                f"Pre-created slot_assignment schema is incomplete: {required - actual}")
        logging.getLogger("alembic.runtime.migration").warning(
            "Reconciling create_all-precreated slot_assignment table")
        return
    op.create_table(
        "slot_assignment",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slot_id", sa.String(length=48), nullable=False),
        sa.Column("program", sa.String(length=8), nullable=False),
        sa.Column("hand", sa.String(length=4), nullable=False, server_default=""),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("serial", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("slot_id"),
    )
    op.create_index("ix_slot_assignment_program", "slot_assignment", ["program"])
    op.create_index("ix_slot_assignment_slot_id", "slot_assignment", ["slot_id"], unique=True)


def downgrade() -> None:
    op.drop_table("slot_assignment")
