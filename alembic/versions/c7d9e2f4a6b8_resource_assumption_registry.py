"""resource and assumption registry foundation

Revision ID: c7d9e2f4a6b8
Revises: b4e2f7a1c8d9
Create Date: 2026-08-27
"""
from typing import Sequence, Union
import logging

from alembic import op
import sqlalchemy as sa


revision: str = "c7d9e2f4a6b8"
down_revision: Union[str, Sequence[str], None] = "b4e2f7a1c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    expected = {
        "resource_pool", "resource_instance", "model_assumption",
        "resource_capacity_version", "operation_resource_binding",
        "external_load_snapshot", "external_load_row", "simulation_snapshot",
        "forecast_constraint_event", "assumption_review",
    }
    if expected <= existing:
        required_columns = {
            "resource_pool": {"id", "code", "site", "name", "resource_type",
                              "capacity_unit", "work_center_no", "active", "retired_at"},
            "resource_instance": {"id", "pool_id", "instance_code", "name", "active"},
            "model_assumption": {"id", "subject_type", "subject_key", "parameter",
                                 "value_json", "basis", "approval_status", "commitment_grade",
                                 "effective_from", "effective_to", "supersedes_id"},
            "resource_capacity_version": {"id", "pool_id", "effective_from", "effective_to",
                                          "status", "capacity_scope", "capacity_schedule_json",
                                          "slot_count", "assumption_id"},
            "operation_resource_binding": {"id", "program", "pool_id", "acquire_op",
                                           "release_op", "requirement_mode", "quantity",
                                           "demand_source", "release_event", "status"},
            "external_load_snapshot": {"id", "captured_at", "source", "schema_version",
                                       "coverage_start", "coverage_end", "content_hash"},
            "external_load_row": {"id", "snapshot_id", "pool_id", "work_date", "source_type",
                                  "load_type", "hours", "quality", "weight"},
            "simulation_snapshot": {"id", "as_of", "horizon_end", "mode", "profile_json",
                                    "readiness", "content_hash"},
            "forecast_constraint_event": {"id", "simulation_snapshot_id", "serial", "program",
                                          "pool_id", "event_type", "reason"},
            "assumption_review": {"id", "assumption_id", "status", "reason", "opened_at"},
        }
        for table, columns in required_columns.items():
            actual = {column["name"] for column in inspector.get_columns(table)}
            if not columns <= actual:
                raise RuntimeError(f"Pre-created {table} schema is incomplete: {columns - actual}")
        logging.getLogger("alembic.runtime.migration").warning(
            "Reconciling create_all-precreated resource-registry tables")
        forecast_columns = {column["name"] for column in inspector.get_columns("forecast_log")}
        if "simulation_snapshot_id" not in forecast_columns:
            with op.batch_alter_table("forecast_log") as batch_op:
                batch_op.add_column(sa.Column("simulation_snapshot_id", sa.Integer(), nullable=True))
                batch_op.create_index("ix_forecast_log_simulation_snapshot_id", ["simulation_snapshot_id"])
                batch_op.create_foreign_key(
                    "fk_forecast_log_simulation_snapshot", "simulation_snapshot",
                    ["simulation_snapshot_id"], ["id"],
                )
        return
    if expected & existing:
        raise RuntimeError("Partial resource-registry schema exists; reconcile before migration")
    op.create_table(
        "resource_pool",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("site", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=16), nullable=False),
        sa.Column("capacity_unit", sa.String(length=8), nullable=False),
        sa.Column("work_center_no", sa.String(length=20), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("retired_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("resource_type IN ('LABOR','MACHINE','TOOL','CURE_STATION','SPACE')"),
        sa.CheckConstraint("capacity_unit IN ('HOURS','SLOTS')"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_resource_pool_code", "resource_pool", ["code"], unique=True)
    op.create_index("ix_resource_pool_site", "resource_pool", ["site"])
    op.create_index("ix_resource_pool_work_center_no", "resource_pool", ["work_center_no"])

    op.create_table(
        "resource_instance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pool_id", sa.Integer(), sa.ForeignKey("resource_pool.id"), nullable=False),
        sa.Column("instance_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("retired_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("pool_id", "instance_code"),
    )
    op.create_index("ix_resource_instance_pool_id", "resource_instance", ["pool_id"])

    op.create_table(
        "model_assumption",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_key", sa.String(length=128), nullable=False),
        sa.Column("parameter", sa.String(length=64), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("basis", sa.String(length=24), nullable=False),
        sa.Column("approval_status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("commitment_grade", sa.String(length=24), nullable=False, server_default="INTERNAL_ONLY"),
        sa.Column("evidence_source", sa.Text(), nullable=True),
        sa.Column("evidence_start", sa.Date(), nullable=True),
        sa.Column("evidence_end", sa.Date(), nullable=True),
        sa.Column("calculation_method", sa.Text(), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=True),
        sa.Column("minimum_evidence_count", sa.Integer(), nullable=True),
        sa.Column("owner", sa.String(length=128), nullable=True),
        sa.Column("approver", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("review_due_at", sa.Date(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("supersedes_id", sa.Integer(), sa.ForeignKey("model_assumption.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("basis IN ('IFS_FACT','MEASURED_ACTUAL','DERIVED_ESTIMATE','OWNER_CONFIRMED','PROVISIONAL_GUESS')"),
        sa.CheckConstraint("approval_status IN ('DRAFT','APPROVED','UNDER_REVIEW','SUPERSEDED')"),
        sa.CheckConstraint("commitment_grade IN ('COMMITMENT_READY','INTERNAL_ONLY')"),
    )
    op.create_index("ix_model_assumption_subject_type", "model_assumption", ["subject_type"])
    op.create_index("ix_model_assumption_subject_key", "model_assumption", ["subject_key"])
    op.create_index("ix_model_assumption_parameter", "model_assumption", ["parameter"])
    op.create_index("ix_model_assumption_effective_from", "model_assumption", ["effective_from"])

    op.create_table(
        "resource_capacity_version",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pool_id", sa.Integer(), sa.ForeignKey("resource_pool.id"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("capacity_scope", sa.String(length=16), nullable=False),
        sa.Column("capacity_schedule_json", sa.Text(), nullable=True),
        sa.Column("slot_count", sa.Integer(), nullable=True),
        sa.Column("calendar_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("external_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("assumption_id", sa.Integer(), sa.ForeignKey("model_assumption.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT','APPROVED','SUPERSEDED')"),
        sa.CheckConstraint("capacity_scope IN ('GROSS_SITE','NET_TRACKED')"),
        sa.UniqueConstraint("pool_id", "effective_from"),
    )
    op.create_index("ix_resource_capacity_version_pool_id", "resource_capacity_version", ["pool_id"])
    op.create_index("ix_resource_capacity_version_effective_from", "resource_capacity_version", ["effective_from"])

    op.create_table(
        "operation_resource_binding",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("program", sa.String(length=8), nullable=False),
        sa.Column("part_no", sa.String(length=100), nullable=True),
        sa.Column("routing_revision", sa.String(length=16), nullable=True),
        sa.Column("routing_alternative", sa.String(length=16), nullable=False, server_default="*"),
        sa.Column("pool_id", sa.Integer(), sa.ForeignKey("resource_pool.id"), nullable=False),
        sa.Column("acquire_op", sa.Integer(), nullable=False),
        sa.Column("release_op", sa.Integer(), nullable=True),
        sa.Column("requirement_mode", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("demand_source", sa.String(length=16), nullable=False),
        sa.Column("release_event", sa.String(length=20), nullable=False),
        sa.Column("min_hold_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("lag_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("instance_code", sa.String(length=64), nullable=True),
        sa.Column("assumption_id", sa.Integer(), sa.ForeignKey("model_assumption.id"), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("requirement_mode IN ('EFFORT','OCCUPANCY')"),
        sa.CheckConstraint("demand_source IN ('LABOR','MACHINE','FIXED')"),
        sa.CheckConstraint("release_event IN ('OP_START','OP_COMPLETE','CURE_COMPLETE','ROUTE_COMPLETE')"),
        sa.CheckConstraint("status IN ('DRAFT','APPROVED','SUPERSEDED')"),
    )
    op.create_index("ix_operation_resource_binding_program", "operation_resource_binding", ["program"])
    op.create_index("ix_operation_resource_binding_pool_id", "operation_resource_binding", ["pool_id"])

    op.create_table(
        "external_load_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("coverage_start", sa.Date(), nullable=False),
        sa.Column("coverage_end", sa.Date(), nullable=False),
        sa.Column("tracked_programs_json", sa.Text(), nullable=False),
        sa.Column("quality_policy_json", sa.Text(), nullable=False),
        sa.Column("assumption_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("content_hash"),
    )
    op.create_index("ix_external_load_snapshot_content_hash", "external_load_snapshot", ["content_hash"], unique=True)

    op.create_table(
        "external_load_row",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("external_load_snapshot.id"), nullable=False),
        sa.Column("pool_id", sa.Integer(), sa.ForeignKey("resource_pool.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("shift", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.String(length=40), nullable=True),
        sa.Column("order_no", sa.String(length=40), nullable=True),
        sa.Column("part_no", sa.String(length=100), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("load_type", sa.String(length=16), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("units", sa.Float(), nullable=True),
        sa.Column("quality", sa.String(length=12), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("quality IN ('OK','SUSPECT','EXCLUDED')"),
    )
    op.create_index("ix_external_load_row_snapshot_id", "external_load_row", ["snapshot_id"])
    op.create_index("ix_external_load_row_pool_id", "external_load_row", ["pool_id"])
    op.create_index("ix_external_load_row_work_date", "external_load_row", ["work_date"])

    op.create_table(
        "simulation_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("horizon_end", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column("assumption_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("external_snapshot_id", sa.Integer(), sa.ForeignKey("external_load_snapshot.id"), nullable=True),
        sa.Column("readiness", sa.String(length=16), nullable=False),
        sa.Column("unresolved_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("content_hash"),
    )
    op.create_index("ix_simulation_snapshot_content_hash", "simulation_snapshot", ["content_hash"], unique=True)

    op.create_table(
        "forecast_constraint_event",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("simulation_snapshot_id", sa.Integer(), sa.ForeignKey("simulation_snapshot.id"), nullable=False),
        sa.Column("serial", sa.String(length=32), nullable=False),
        sa.Column("program", sa.String(length=8), nullable=False),
        sa.Column("pool_id", sa.Integer(), sa.ForeignKey("resource_pool.id"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("wait_start", sa.DateTime(), nullable=True),
        sa.Column("wait_end", sa.DateTime(), nullable=True),
        sa.Column("wait_hours", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("gross_capacity", sa.Float(), nullable=True),
        sa.Column("external_load", sa.Float(), nullable=True),
        sa.Column("schedulable_capacity", sa.Float(), nullable=True),
        sa.Column("assumption_ids_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_forecast_constraint_event_simulation_snapshot_id", "forecast_constraint_event", ["simulation_snapshot_id"])
    op.create_index("ix_forecast_constraint_event_serial", "forecast_constraint_event", ["serial"])
    op.create_index("ix_forecast_constraint_event_program", "forecast_constraint_event", ["program"])
    op.create_index("ix_forecast_constraint_event_pool_id", "forecast_constraint_event", ["pool_id"])

    op.create_table(
        "assumption_review",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("assumption_id", sa.Integer(), sa.ForeignKey("model_assumption.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED')"),
    )
    op.create_index("ix_assumption_review_assumption_id", "assumption_review", ["assumption_id"])

    with op.batch_alter_table("forecast_log") as batch_op:
        batch_op.add_column(sa.Column("simulation_snapshot_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_forecast_log_simulation_snapshot_id", ["simulation_snapshot_id"])
        batch_op.create_foreign_key(
            "fk_forecast_log_simulation_snapshot", "simulation_snapshot",
            ["simulation_snapshot_id"], ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("forecast_log") as batch_op:
        batch_op.drop_constraint("fk_forecast_log_simulation_snapshot", type_="foreignkey")
        batch_op.drop_index("ix_forecast_log_simulation_snapshot_id")
        batch_op.drop_column("simulation_snapshot_id")
    op.drop_table("assumption_review")
    op.drop_table("forecast_constraint_event")
    op.drop_table("simulation_snapshot")
    op.drop_table("external_load_row")
    op.drop_table("external_load_snapshot")
    op.drop_table("operation_resource_binding")
    op.drop_table("resource_capacity_version")
    op.drop_table("model_assumption")
    op.drop_table("resource_instance")
    op.drop_table("resource_pool")
