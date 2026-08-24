"""add program table (config-driven program registry)

Revision ID: b4e2f7a1c8d9
Revises: a3f1c9d4e5b6
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4e2f7a1c8d9"
down_revision: Union[str, Sequence[str], None] = "a3f1c9d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "program",
        sa.Column("code", sa.String(length=8), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("plant", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(length=16), nullable=False),
        sa.Column("part_nos", sa.Text(), nullable=False),
        sa.Column("pack_op", sa.Integer(), nullable=False),
        sa.Column("ship_op", sa.Integer(), nullable=False),
        sa.Column("floor_op", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ops_json", sa.Text(), nullable=False),
        sa.Column("cures_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("milestones_json", sa.Text(), nullable=False),
        sa.Column("ceilings_json", sa.Text(), nullable=False),
        sa.Column("crew_by_op_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("dpas", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("train_threshold", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("rtg_source", sa.String(length=255), nullable=True),
        sa.Column("hand_split", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hand_map_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("program")
