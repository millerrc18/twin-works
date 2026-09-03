"""add append-only resource availability events

Revision ID: 0a1b2c3d4e5f
Revises: fdb4c5d6e7f8
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models import (
    RESOURCE_AVAILABILITY_CAPACITY_TRIGGER,
    RESOURCE_AVAILABILITY_EVENT_VALIDATE_TRIGGER,
    _append_only_insert_guard,
    _append_only_triggers,
)


revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "fdb4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "resource_availability_event"
IDENTITY = (
    "id = NEW.id OR event_key = NEW.event_key OR "
    "(outage_key = NEW.outage_key AND sequence = NEW.sequence)"
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("outage_key", sa.String(length=160), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("pool_id", sa.Integer(), nullable=False),
        sa.Column("instance_code", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("unavailable_quantity", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason_code", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("authority_role", sa.String(length=24), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pool_id"], ["resource_pool.id"]),
        sa.UniqueConstraint("event_key"),
        sa.UniqueConstraint("outage_key", "sequence"),
        sa.CheckConstraint(
            "event_type IN ('OUTAGE_OPEN','RETURN_TO_SERVICE','EXTEND','CANCEL','VOID')"),
        sa.CheckConstraint(
            "reason_code IN ('TOOL_SHOP','MAINTENANCE','REPAIR','CALIBRATION','OTHER')"),
        sa.CheckConstraint("authority_role IN ('DATA_ADMIN','PROGRAM_OWNER')"),
        sa.CheckConstraint("unavailable_quantity > 0"),
        sa.CheckConstraint("length(trim(reason)) > 0"),
        sa.CheckConstraint("length(trim(actor)) > 0"),
        sa.CheckConstraint("json_valid(evidence_json)"),
        sa.CheckConstraint(
            "(event_type = 'OUTAGE_OPEN' AND sequence = 1 "
            "AND effective_at IS NOT NULL AND expected_end_at IS NOT NULL "
            "AND expected_end_at > effective_at) OR "
            "(event_type = 'EXTEND' AND sequence > 1 "
            "AND effective_at IS NULL AND expected_end_at IS NOT NULL) OR "
            "(event_type = 'RETURN_TO_SERVICE' AND sequence > 1 "
            "AND effective_at IS NOT NULL AND expected_end_at IS NULL) OR "
            "(event_type IN ('CANCEL','VOID') AND sequence > 1 "
            "AND effective_at IS NULL AND expected_end_at IS NULL)"
        ),
    )
    op.create_index(
        "ix_resource_availability_event_event_key", TABLE, ["event_key"], unique=True)
    op.create_index(
        "ix_resource_availability_event_outage_key", TABLE, ["outage_key"])
    op.create_index(
        "ix_resource_availability_event_pool_id", TABLE, ["pool_id"])
    op.create_index(
        "ix_resource_availability_event_event_type", TABLE, ["event_type"])
    op.execute(RESOURCE_AVAILABILITY_EVENT_VALIDATE_TRIGGER)
    op.execute(RESOURCE_AVAILABILITY_CAPACITY_TRIGGER)
    for trigger in _append_only_triggers(TABLE):
        op.execute(trigger)
    op.execute(_append_only_insert_guard(TABLE, IDENTITY))


def downgrade() -> None:
    op.drop_table(TABLE)