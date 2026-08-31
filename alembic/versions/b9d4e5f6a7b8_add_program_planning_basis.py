"""add explicit program planning basis and forecast targets

Revision ID: b9d4e5f6a7b8
Revises: a8c3d4e5f6a7
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a8c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    program_columns = {column["name"] for column in inspector.get_columns("program")}
    forecast_columns = {column["name"] for column in inspector.get_columns("forecast_log")}

    if "configured_planning_basis" not in program_columns:
        with op.batch_alter_table("program") as batch_op:
            batch_op.add_column(sa.Column(
                "configured_planning_basis", sa.String(length=24), nullable=False,
                server_default="NONE"))
            batch_op.add_column(sa.Column("plan_label", sa.String(length=64), nullable=True))
            batch_op.add_column(sa.Column("plan_version", sa.String(length=64), nullable=True))
            batch_op.create_check_constraint(
                "ck_program_configured_planning_basis",
                "configured_planning_basis IN ('PLAN_SLOTS','CONTRACT_DATES','NONE')",
            )
    missing_forecast = {
        "plan_target_date", "comparison_target_date", "planning_basis",
        "plan_label", "model_epoch_key",
    } - forecast_columns
    if missing_forecast:
        with op.batch_alter_table("forecast_log") as batch_op:
            if "plan_target_date" in missing_forecast:
                batch_op.add_column(sa.Column("plan_target_date", sa.Date(), nullable=True))
            if "comparison_target_date" in missing_forecast:
                batch_op.add_column(sa.Column("comparison_target_date", sa.Date(), nullable=True))
            if "planning_basis" in missing_forecast:
                batch_op.add_column(sa.Column("planning_basis", sa.String(length=24), nullable=True))
            if "plan_label" in missing_forecast:
                batch_op.add_column(sa.Column("plan_label", sa.String(length=64), nullable=True))
            if "model_epoch_key" in missing_forecast:
                batch_op.add_column(sa.Column("model_epoch_key", sa.String(length=64), nullable=True))

    op.execute("""
        UPDATE program
        SET configured_planning_basis = CASE
                WHEN code IN ('ELEV','RAD') THEN 'PLAN_SLOTS'
                WHEN code = 'AEGIS' THEN 'CONTRACT_DATES'
                ELSE configured_planning_basis
            END,
            plan_label = CASE
                WHEN code IN ('ELEV','RAD') THEN 'RTG'
                WHEN code = 'AEGIS' THEN 'Contract'
                ELSE plan_label
            END,
            plan_version = CASE WHEN code IN ('ELEV','RAD') THEN '2026' ELSE plan_version END
            ,rtg_source = CASE
                WHEN code IN ('ELEV','RAD') THEN COALESCE(rtg_source, 'rtg_targets.json')
                ELSE rtg_source
            END
    """)
    op.execute("""
        UPDATE forecast_log
        SET planning_basis = CASE
                WHEN program IN ('ELEV','RAD') THEN 'PLAN_SLOTS'
                WHEN program = 'AEGIS' THEN 'CONTRACT_DATES'
                ELSE NULL
            END,
            plan_label = CASE
                WHEN program IN ('ELEV','RAD') THEN 'RTG'
                WHEN program = 'AEGIS' THEN 'Contract'
                ELSE NULL
            END,
            plan_target_date = CASE
                WHEN program IN ('ELEV','RAD') THEN contract_date ELSE NULL END,
            comparison_target_date = contract_date
    """)
    op.execute("UPDATE forecast_log SET contract_date = NULL WHERE program IN ('ELEV','RAD')")


def downgrade() -> None:
    with op.batch_alter_table("forecast_log") as batch_op:
        batch_op.drop_column("model_epoch_key")
        batch_op.drop_column("plan_label")
        batch_op.drop_column("planning_basis")
        batch_op.drop_column("comparison_target_date")
        batch_op.drop_column("plan_target_date")
    with op.batch_alter_table("program") as batch_op:
        batch_op.drop_constraint("ck_program_configured_planning_basis", type_="check")
        batch_op.drop_column("plan_version")
        batch_op.drop_column("plan_label")
        batch_op.drop_column("configured_planning_basis")
