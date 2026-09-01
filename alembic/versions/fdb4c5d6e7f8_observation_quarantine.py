"""add append-only observation quarantine events

Revision ID: fdb4c5d6e7f8
Revises: ecf2a3b4c5d6
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models import (
    QUARANTINE_EVENT_VALIDATE_TRIGGER,
    _append_only_insert_guard,
    _append_only_triggers,
)


revision: str = "fdb4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "ecf2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "observation_quarantine_event"
IDENTITY = (
    "id = NEW.id OR event_key = NEW.event_key OR "
    "(quarantine_key = NEW.quarantine_key AND sequence = NEW.sequence)"
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("quarantine_key", sa.String(length=160), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stream_key", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("part_no", sa.String(length=100), nullable=False),
        sa.Column("order_no", sa.String(length=40), nullable=False),
        sa.Column("serial", sa.String(length=32), nullable=True),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("event_key"),
        sa.UniqueConstraint("quarantine_key", "sequence"),
        sa.CheckConstraint("event_type IN ('OPEN','RESOLVE','REOPEN')"),
        sa.CheckConstraint("reason_code IN ('TERMINAL_COMPLETE_STATE_OPEN')"),
    )
    op.create_index("ix_observation_quarantine_event_event_key", TABLE, ["event_key"], unique=True)
    op.create_index("ix_observation_quarantine_event_quarantine_key", TABLE, ["quarantine_key"])
    op.create_index("ix_observation_quarantine_event_stream_key", TABLE, ["stream_key"])
    op.create_index("ix_observation_quarantine_event_order_no", TABLE, ["order_no"])
    op.create_index("ix_observation_quarantine_event_event_type", TABLE, ["event_type"])
    op.execute(QUARANTINE_EVENT_VALIDATE_TRIGGER)
    for trigger in _append_only_triggers(TABLE):
        op.execute(trigger)
    op.execute(_append_only_insert_guard(TABLE, IDENTITY))


def downgrade() -> None:
    op.drop_table(TABLE)
