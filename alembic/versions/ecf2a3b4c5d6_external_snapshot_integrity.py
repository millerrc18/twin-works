"""protect immutable external-load snapshots

Revision ID: ecf2a3b4c5d6
Revises: dbe1f2a3b4c5
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op

from app.models import _append_only_insert_guard, _append_only_triggers


revision: str = "ecf2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "dbe1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = {
    "external_load_snapshot": "id = NEW.id OR content_hash = NEW.content_hash",
    "external_load_row": "id = NEW.id",
}


def _drop_triggers() -> None:
    for table in TABLES:
        for suffix in ("insert", "update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_{suffix}")


def upgrade() -> None:
    _drop_triggers()
    for table, identity in TABLES.items():
        for trigger in _append_only_triggers(table):
            op.execute(trigger)
        op.execute(_append_only_insert_guard(table, identity))


def downgrade() -> None:
    _drop_triggers()
