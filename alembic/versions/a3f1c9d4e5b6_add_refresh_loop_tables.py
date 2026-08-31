"""add refresh-loop tables: position_state, model_history, sync_run

Revision ID: a3f1c9d4e5b6
Revises: e2d2104bccb8
Create Date: 2026-08-22

"""
from typing import Sequence, Union
import logging

from alembic import op
import sqlalchemy as sa


revision: str = "a3f1c9d4e5b6"
down_revision: Union[str, Sequence[str], None] = "e2d2104bccb8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    expected = {"position_state", "model_history", "sync_run"}
    if expected <= existing:
        required = {
            "position_state": {"id", "so", "program", "serial", "maxop", "last_clock",
                               "due", "closed", "pack", "source", "synced_at"},
            "model_history": {"id", "at", "program", "mode", "n_scored", "threshold",
                              "bias", "mae", "source"},
            "sync_run": {"id", "kind", "active", "stage", "result_json", "error",
                         "started_at", "finished_at"},
        }
        for table, columns in required.items():
            actual = {column["name"] for column in inspector.get_columns(table)}
            if not columns <= actual:
                raise RuntimeError(f"Pre-created {table} schema is incomplete: {columns - actual}")
        logging.getLogger("alembic.runtime.migration").warning(
            "Reconciling create_all-precreated refresh-loop tables")
        return
    if expected & existing:
        raise RuntimeError("Partial refresh-loop schema exists; reconcile before migration")
    op.create_table(
        "position_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("so", sa.String(length=12), nullable=False),
        sa.Column("program", sa.String(length=8), nullable=False),
        sa.Column("serial", sa.String(length=32), nullable=False),
        sa.Column("maxop", sa.Integer(), nullable=True),
        sa.Column("last_clock", sa.Date(), nullable=True),
        sa.Column("due", sa.Date(), nullable=True),
        sa.Column("closed", sa.Date(), nullable=True),
        sa.Column("pack", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=12), nullable=False, server_default="baseline"),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_position_state_so", "position_state", ["so"], unique=True)
    op.create_index("ix_position_state_program", "position_state", ["program"])

    op.create_table(
        "model_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("program", sa.String(length=8), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("n_scored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("threshold", sa.Integer(), nullable=True),
        sa.Column("bias", sa.Float(), nullable=True),
        sa.Column("mae", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="sync"),
    )
    op.create_index("ix_model_history_at", "model_history", ["at"])
    op.create_index("ix_model_history_program", "model_history", ["program"])

    op.create_table(
        "sync_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stage", sa.String(length=24), nullable=False, server_default="starting"),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sync_run_active", "sync_run", ["active"])


def downgrade() -> None:
    op.drop_index("ix_sync_run_active", table_name="sync_run")
    op.drop_table("sync_run")
    op.drop_index("ix_model_history_program", table_name="model_history")
    op.drop_index("ix_model_history_at", table_name="model_history")
    op.drop_table("model_history")
    op.drop_index("ix_position_state_program", table_name="position_state")
    op.drop_index("ix_position_state_so", table_name="position_state")
    op.drop_table("position_state")
