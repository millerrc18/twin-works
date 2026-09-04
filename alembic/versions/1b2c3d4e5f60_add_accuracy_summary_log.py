"""add immutable Accuracy v1.0 summary log

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-09-03
"""
from typing import Sequence, Union
import logging

from alembic import op
import sqlalchemy as sa

from app.models import _append_only_insert_guard, _append_only_triggers


revision: str = "1b2c3d4e5f60"
down_revision: Union[str, Sequence[str], None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "accuracy_summary_log"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if TABLE in set(inspector.get_table_names()):
        required = {
            "id", "as_of_date", "captured_at", "program", "horizon_days",
            "formula_version", "score", "confidence", "sample_size",
            "observed_unit_count", "missing_window_count", "post_ship_record_count",
            "mae_days", "bias_days", "hit3_pct", "hit7_pct", "p80_sample_size",
            "p80_coverage_pct", "p80_wilson_low_pct", "p80_wilson_high_pct",
            "source_forecast_ids_json", "cohort_json", "cohort_hash", "content_hash",
        }
        actual = {column["name"] for column in inspector.get_columns(TABLE)}
        if not required <= actual:
            raise RuntimeError(
                f"Pre-created accuracy_summary_log schema is incomplete: {required - actual}")
        logging.getLogger("alembic.runtime.migration").warning(
            "Reconciling create_all-precreated accuracy_summary_log table")
        for trigger in _append_only_triggers(TABLE):
            op.execute(trigger)
        op.execute(_append_only_insert_guard(
            TABLE, "id = NEW.id OR content_hash = NEW.content_hash"))
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("program", sa.String(length=8), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("formula_version", sa.String(length=24), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("observed_unit_count", sa.Integer(), nullable=False),
        sa.Column("missing_window_count", sa.Integer(), nullable=False),
        sa.Column("post_ship_record_count", sa.Integer(), nullable=False),
        sa.Column("mae_days", sa.Float(), nullable=True),
        sa.Column("bias_days", sa.Float(), nullable=True),
        sa.Column("hit3_pct", sa.Float(), nullable=True),
        sa.Column("hit7_pct", sa.Float(), nullable=True),
        sa.Column("p80_sample_size", sa.Integer(), nullable=False),
        sa.Column("p80_coverage_pct", sa.Float(), nullable=True),
        sa.Column("p80_wilson_low_pct", sa.Float(), nullable=True),
        sa.Column("p80_wilson_high_pct", sa.Float(), nullable=True),
        sa.Column("source_forecast_ids_json", sa.Text(), nullable=False),
        sa.Column("cohort_json", sa.Text(), nullable=False),
        sa.Column("cohort_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("content_hash"),
        sa.CheckConstraint("horizon_days IN (7,14,21)"),
        sa.CheckConstraint(
            "confidence IN ('INSUFFICIENT','PRELIMINARY','DEVELOPING','ESTABLISHED')"),
        sa.CheckConstraint("sample_size >= 0"),
        sa.CheckConstraint("observed_unit_count >= sample_size"),
        sa.CheckConstraint("missing_window_count >= 0"),
        sa.CheckConstraint("post_ship_record_count >= 0"),
        sa.CheckConstraint("p80_sample_size >= 0 AND p80_sample_size <= sample_size"),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)"),
    )
    op.create_index("ix_accuracy_summary_log_as_of_date", TABLE, ["as_of_date"])
    op.create_index("ix_accuracy_summary_log_captured_at", TABLE, ["captured_at"])
    op.create_index("ix_accuracy_summary_log_program", TABLE, ["program"])
    op.create_index("ix_accuracy_summary_log_cohort_hash", TABLE, ["cohort_hash"])
    op.create_index(
        "ix_accuracy_summary_log_content_hash", TABLE, ["content_hash"], unique=True)
    for trigger in _append_only_triggers(TABLE):
        op.execute(trigger)
    op.execute(_append_only_insert_guard(
        TABLE, "id = NEW.id OR content_hash = NEW.content_hash"))


def downgrade() -> None:
    op.drop_table(TABLE)