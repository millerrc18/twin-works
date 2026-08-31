"""harden model epoch and simulation snapshot audit records

Revision ID: f7b2c3d4e5f6
Revises: e6a1b2c3d4e5
Create Date: 2026-08-28
"""
from typing import Sequence, Union

from alembic import op

from app.models import (
    MODEL_EPOCH_ACTIVATION_VALIDATE_TRIGGER,
    MODEL_EPOCH_TRANSITION_VALIDATE_TRIGGER,
    _append_only_insert_guard,
    _append_only_triggers,
)


revision: str = "f7b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABLE_TABLES = (
    "model_epoch",
    "model_epoch_transition",
    "program_epoch_activation",
    "simulation_snapshot",
    "simulation_snapshot_epoch",
    "forecast_constraint_event",
)
INSERT_IDENTITIES = {
    "model_epoch": (
        "id = NEW.id OR epoch_key = NEW.epoch_key "
        "OR (program = NEW.program AND definition_hash = NEW.definition_hash)"),
    "model_epoch_transition": (
        "id = NEW.id OR (epoch_id = NEW.epoch_id AND sequence = NEW.sequence)"),
    "program_epoch_activation": "id = NEW.id",
    "simulation_snapshot": "id = NEW.id OR content_hash = NEW.content_hash",
    "simulation_snapshot_epoch": (
        "simulation_snapshot_id = NEW.simulation_snapshot_id AND program = NEW.program"),
    "forecast_constraint_event": "id = NEW.id",
}


def _drop_governance_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_program_epoch_activation_validate")
    op.execute("DROP TRIGGER IF EXISTS trg_model_epoch_transition_validate")
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_update")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_delete")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_insert")


def _install_governance_triggers() -> None:
    op.execute(MODEL_EPOCH_TRANSITION_VALIDATE_TRIGGER)
    op.execute(MODEL_EPOCH_ACTIVATION_VALIDATE_TRIGGER)
    for table in IMMUTABLE_TABLES:
        for trigger in _append_only_triggers(table):
            op.execute(trigger)
        op.execute(_append_only_insert_guard(table, INSERT_IDENTITIES[table]))


def upgrade() -> None:
    _drop_governance_triggers()
    _install_governance_triggers()


def downgrade() -> None:
    # The preceding revision owns the same core validation triggers. Reinstall the
    # current definitions so downgrading never leaves epoch records unguarded.
    _drop_governance_triggers()
    _install_governance_triggers()
