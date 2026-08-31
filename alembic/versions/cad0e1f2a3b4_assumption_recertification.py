"""add assumption evidence and recertification governance

Revision ID: cad0e1f2a3b4
Revises: b9d4e5f6a7b8
Create Date: 2026-08-31
"""
from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models import (
    APPROVED_ASSUMPTION_EVIDENCE_TRIGGER,
    APPROVED_ASSUMPTION_TRIGGER,
    ASSUMPTION_REVIEW_DELETE_TRIGGER,
    ASSUMPTION_REVIEW_RESOLUTION_TRIGGER,
)


revision: str = "cad0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b9d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _backfill_evidence() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id, subject_type, subject_key, parameter, basis, evidence_source,
               evidence_start, evidence_end, calculation_method, evidence_count,
               owner, approver, approved_at, created_at, evidence_json
        FROM model_assumption
    """)).mappings()
    for row in rows:
        if row["evidence_json"] not in (None, "", "{}"):
            continue
        source = row["evidence_source"] or (
            f"migrated:{row['subject_type']}:{row['subject_key']}:{row['parameter']}")
        payload = {
            "schema_version": 1,
            "source_refs": [source],
            "captured_by": row["approver"] or row["owner"] or "TwinWorks migration",
            "captured_at": str(row["approved_at"] or row["created_at"]),
            "method": row["calculation_method"] or row["basis"],
            "migration": "cad0e1f2a3b4",
        }
        if row["evidence_start"] or row["evidence_end"]:
            payload["window"] = {
                "start": str(row["evidence_start"]) if row["evidence_start"] else None,
                "end": str(row["evidence_end"]) if row["evidence_end"] else None,
            }
        if row["evidence_count"] is not None:
            payload["sample_count"] = row["evidence_count"]
        bind.execute(
            sa.text("""
                UPDATE model_assumption
                SET evidence_schema_version = 1, evidence_json = :evidence_json
                WHERE id = :id
            """),
            {"id": row["id"], "evidence_json": json.dumps(
                payload, sort_keys=True, separators=(",", ":"))},
        )


def _backfill_reviews() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE assumption_review
        SET review_key = COALESCE(review_key, 'legacy:' || id),
            review_type = COALESCE(review_type, 'MANUAL'),
            evidence_json = COALESCE(evidence_json, '{}'),
            opened_by = COALESCE(opened_by, 'TwinWorks migration')
    """))


def _drop_managed_triggers() -> None:
    for name in (
        "trg_model_assumption_approved_immutable",
        "trg_model_assumption_evidence_immutable",
        "trg_assumption_review_resolution_immutable",
        "trg_assumption_review_delete_immutable",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")


def _install_triggers() -> None:
    _drop_managed_triggers()
    op.execute(APPROVED_ASSUMPTION_TRIGGER)
    op.execute(APPROVED_ASSUMPTION_EVIDENCE_TRIGGER)
    op.execute(ASSUMPTION_REVIEW_RESOLUTION_TRIGGER)
    op.execute(ASSUMPTION_REVIEW_DELETE_TRIGGER)


def upgrade() -> None:
    # SQLite table rebuilds can preserve existing triggers until the old table is
    # dropped. Disable our guards while adding and backfilling the new provenance
    # fields, then reinstall the complete definitions at the end.
    _drop_managed_triggers()
    assumption_columns = _column_names("model_assumption")
    if "evidence_schema_version" not in assumption_columns:
        with op.batch_alter_table("model_assumption") as batch_op:
            batch_op.add_column(sa.Column(
                "evidence_schema_version", sa.Integer(), nullable=False, server_default="1"))
            batch_op.add_column(sa.Column(
                "evidence_json", sa.Text(), nullable=False, server_default="{}"))

    review_columns = _column_names("assumption_review")
    missing_review_columns = {
        "review_key", "review_type", "evidence_json", "owner", "opened_by",
        "resolved_by", "resolution", "successor_assumption_id",
    } - review_columns
    if missing_review_columns:
        with op.batch_alter_table("assumption_review") as batch_op:
            if "review_key" in missing_review_columns:
                batch_op.add_column(sa.Column("review_key", sa.String(length=160), nullable=True))
            if "review_type" in missing_review_columns:
                batch_op.add_column(sa.Column("review_type", sa.String(length=24), nullable=True))
            if "evidence_json" in missing_review_columns:
                batch_op.add_column(sa.Column(
                    "evidence_json", sa.Text(), nullable=False, server_default="{}"))
            if "owner" in missing_review_columns:
                batch_op.add_column(sa.Column("owner", sa.String(length=128), nullable=True))
            if "opened_by" in missing_review_columns:
                batch_op.add_column(sa.Column(
                    "opened_by", sa.String(length=128), nullable=False,
                    server_default="TwinWorks migration"))
            if "resolved_by" in missing_review_columns:
                batch_op.add_column(sa.Column("resolved_by", sa.String(length=128), nullable=True))
            if "resolution" in missing_review_columns:
                batch_op.add_column(sa.Column("resolution", sa.String(length=24), nullable=True))
            if "successor_assumption_id" in missing_review_columns:
                batch_op.add_column(sa.Column(
                    "successor_assumption_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_assumption_review_successor", "model_assumption",
                    ["successor_assumption_id"], ["id"],
                )

    _drop_managed_triggers()
    _backfill_evidence()
    _backfill_reviews()

    review_columns = _column_names("assumption_review")
    if {"review_key", "review_type"} <= review_columns:
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(
            "assumption_review")}
        with op.batch_alter_table("assumption_review") as batch_op:
            batch_op.alter_column("review_key", existing_type=sa.String(length=160),
                                  nullable=False)
            batch_op.alter_column("review_type", existing_type=sa.String(length=24),
                                  nullable=False)
            if "ix_assumption_review_review_key" not in indexes:
                batch_op.create_index(
                    "ix_assumption_review_review_key", ["review_key"], unique=True)
            checks = [item.get("sqltext", "") for item in
                      sa.inspect(op.get_bind()).get_check_constraints("assumption_review")]
            if not any("review_type IN" in text for text in checks):
                batch_op.create_check_constraint(
                    "ck_assumption_review_type",
                    "review_type IN ('EXPIRY','MISSING_REVIEW_DATE','DRIFT',"
                    "'SPARSE_EVIDENCE','MANUAL')",
                )
            if not any("resolution IS NULL" in text for text in checks):
                batch_op.create_check_constraint(
                    "ck_assumption_review_resolution",
                    "resolution IS NULL OR resolution IN "
                    "('RECERTIFIED','SUPERSEDED','DISMISSED')",
                )
    _install_triggers()


def downgrade() -> None:
    for name in (
        "trg_model_assumption_evidence_immutable",
        "trg_assumption_review_resolution_immutable",
        "trg_assumption_review_delete_immutable",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    with op.batch_alter_table("assumption_review") as batch_op:
        batch_op.drop_constraint("ck_assumption_review_resolution", type_="check")
        batch_op.drop_constraint("ck_assumption_review_type", type_="check")
        batch_op.drop_constraint("fk_assumption_review_successor", type_="foreignkey")
        batch_op.drop_index("ix_assumption_review_review_key")
        batch_op.drop_column("successor_assumption_id")
        batch_op.drop_column("resolution")
        batch_op.drop_column("resolved_by")
        batch_op.drop_column("opened_by")
        batch_op.drop_column("owner")
        batch_op.drop_column("evidence_json")
        batch_op.drop_column("review_type")
        batch_op.drop_column("review_key")
    with op.batch_alter_table("model_assumption") as batch_op:
        batch_op.drop_column("evidence_json")
        batch_op.drop_column("evidence_schema_version")
    op.execute("DROP TRIGGER IF EXISTS trg_model_assumption_approved_immutable")
    op.execute(APPROVED_ASSUMPTION_TRIGGER)
