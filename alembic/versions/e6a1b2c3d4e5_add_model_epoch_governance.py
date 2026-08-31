"""add append-only model epoch governance

Revision ID: e6a1b2c3d4e5
Revises: d8ea03f5b7c9
Create Date: 2026-08-28
"""
from typing import Sequence, Union
import logging

from alembic import op
import sqlalchemy as sa

from app.models import (
    MODEL_EPOCH_ACTIVATION_VALIDATE_TRIGGER,
    MODEL_EPOCH_TRANSITION_VALIDATE_TRIGGER,
    _append_only_triggers,
)


revision: str = "e6a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "d8ea03f5b7c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "model_epoch",
    "model_epoch_transition",
    "program_epoch_activation",
    "simulation_snapshot_epoch",
)
IMMUTABLE_TABLES = TABLES + ("simulation_snapshot", "forecast_constraint_event")


def _install_triggers() -> None:
    op.execute(MODEL_EPOCH_TRANSITION_VALIDATE_TRIGGER)
    op.execute(MODEL_EPOCH_ACTIVATION_VALIDATE_TRIGGER)
    for table in IMMUTABLE_TABLES:
        for trigger in _append_only_triggers(table):
            op.execute(trigger)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    expected = set(TABLES)
    if expected <= existing:
        required = {
            "model_epoch": {
                "id", "epoch_key", "program", "epoch_kind", "predecessor_epoch_id",
                "label", "resource_mode", "definition_json", "definition_hash",
                "created_by", "created_at",
            },
            "model_epoch_transition": {
                "id", "epoch_id", "sequence", "from_state", "to_state",
                "authority_role", "actor", "rationale", "evidence_json",
                "transitioned_at",
            },
            "program_epoch_activation": {
                "id", "program", "epoch_id", "transition_id", "action",
                "authority_role", "actor", "rationale", "activated_at",
            },
            "simulation_snapshot_epoch": {
                "simulation_snapshot_id", "program", "model_epoch_id",
            },
        }
        for table, columns in required.items():
            actual = {column["name"] for column in inspector.get_columns(table)}
            if not columns <= actual:
                raise RuntimeError(
                    f"Pre-created {table} schema is incomplete: {columns - actual}")
        logging.getLogger("alembic.runtime.migration").warning(
            "Reconciling create_all-precreated model-epoch tables")
        _install_triggers()
        return
    if expected & existing:
        raise RuntimeError("Partial model-epoch schema exists; reconcile before migration")

    op.create_table(
        "model_epoch",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("epoch_key", sa.String(length=64), nullable=False),
        sa.Column("program", sa.String(length=8), nullable=False),
        sa.Column("epoch_kind", sa.String(length=24), nullable=False),
        sa.Column("predecessor_epoch_id", sa.Integer(),
                  sa.ForeignKey("model_epoch.id"), nullable=True),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("resource_mode", sa.String(length=16), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("epoch_kind IN ('LEGACY_BASELINE','CANDIDATE')"),
        sa.CheckConstraint("resource_mode IN ('LEGACY','DB_SHADOW','DB_ACTIVE')"),
        sa.UniqueConstraint("epoch_key"),
        sa.UniqueConstraint("program", "definition_hash"),
    )
    op.create_index("ix_model_epoch_epoch_key", "model_epoch", ["epoch_key"], unique=True)
    op.create_index("ix_model_epoch_program", "model_epoch", ["program"])
    op.create_index("ix_model_epoch_definition_hash", "model_epoch", ["definition_hash"])

    op.create_table(
        "model_epoch_transition",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("epoch_id", sa.Integer(), sa.ForeignKey("model_epoch.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(length=24), nullable=True),
        sa.Column("to_state", sa.String(length=24), nullable=False),
        sa.Column("authority_role", sa.String(length=24), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("transitioned_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "to_state IN ('DRAFT','OBSERVE','PROVISIONAL','COMMITMENT_READY',"
            "'PAUSED','ARCHIVED','DEPRECATED')"),
        sa.CheckConstraint(
            "from_state IS NULL OR from_state IN ('DRAFT','OBSERVE','PROVISIONAL',"
            "'COMMITMENT_READY','PAUSED','ARCHIVED','DEPRECATED')"),
        sa.CheckConstraint(
            "authority_role IN ('DATA_ADMIN','IE_FLOOR','PROGRAM_SCHEDULING')"),
        sa.UniqueConstraint("epoch_id", "sequence"),
    )
    op.create_index("ix_model_epoch_transition_epoch_id", "model_epoch_transition", ["epoch_id"])
    op.create_index("ix_model_epoch_transition_to_state", "model_epoch_transition", ["to_state"])

    op.create_table(
        "program_epoch_activation",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("program", sa.String(length=8), nullable=False),
        sa.Column("epoch_id", sa.Integer(), sa.ForeignKey("model_epoch.id"), nullable=False),
        sa.Column("transition_id", sa.Integer(),
                  sa.ForeignKey("model_epoch_transition.id"), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("authority_role", sa.String(length=24), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("action IN ('PUBLISH','ROLLBACK')"),
        sa.CheckConstraint("authority_role = 'PROGRAM_SCHEDULING'"),
    )
    op.create_index("ix_program_epoch_activation_program", "program_epoch_activation", ["program"])
    op.create_index("ix_program_epoch_activation_epoch_id", "program_epoch_activation", ["epoch_id"])
    op.create_index("ix_program_epoch_activation_transition_id", "program_epoch_activation", ["transition_id"])

    op.create_table(
        "simulation_snapshot_epoch",
        sa.Column("simulation_snapshot_id", sa.Integer(),
                  sa.ForeignKey("simulation_snapshot.id"), primary_key=True),
        sa.Column("program", sa.String(length=8), primary_key=True),
        sa.Column("model_epoch_id", sa.Integer(),
                  sa.ForeignKey("model_epoch.id"), nullable=False),
    )
    op.create_index("ix_simulation_snapshot_epoch_model_epoch_id",
                    "simulation_snapshot_epoch", ["model_epoch_id"])
    _install_triggers()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_program_epoch_activation_validate")
    op.execute("DROP TRIGGER IF EXISTS trg_model_epoch_transition_validate")
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_update")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_delete")
    op.drop_table("simulation_snapshot_epoch")
    op.drop_table("program_epoch_activation")
    op.drop_table("model_epoch_transition")
    op.drop_table("model_epoch")
