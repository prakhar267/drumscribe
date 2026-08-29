"""add provider provenance

Revision ID: b3f764a9c2e1
Revises: d90d268d92dc
Create Date: 2026-08-29 22:18:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b3f764a9c2e1"
down_revision: str | None = "d90d268d92dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("provider_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False)
        )
        batch_op.add_column(sa.Column("total_provider_cost", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("provider_cost_currency", sa.String(length=32), nullable=True))
        batch_op.create_check_constraint(
            "job_provider_cost", "total_provider_cost IS NULL OR total_provider_cost >= 0"
        )

    with op.batch_alter_table("model_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "provider_category",
                sa.String(length=64),
                server_default="TEST_FIXTURE",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("provider_request_id", sa.String(length=255)))
        batch_op.add_column(
            sa.Column(
                "raw_provider_metadata",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("error_category", sa.String(length=64)))
        batch_op.add_column(sa.Column("cost_amount", sa.Float()))
        batch_op.add_column(sa.Column("cost_currency", sa.String(length=32)))
        batch_op.add_column(sa.Column("retention_expires_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("contract_reference", sa.String(length=255)))
        batch_op.create_check_constraint(
            "model_run_cost", "cost_amount IS NULL OR cost_amount >= 0"
        )


def downgrade() -> None:
    with op.batch_alter_table("model_runs", schema=None) as batch_op:
        batch_op.drop_constraint("model_run_cost", type_="check")
        batch_op.drop_column("contract_reference")
        batch_op.drop_column("retention_expires_at")
        batch_op.drop_column("cost_currency")
        batch_op.drop_column("cost_amount")
        batch_op.drop_column("error_category")
        batch_op.drop_column("raw_provider_metadata")
        batch_op.drop_column("provider_request_id")
        batch_op.drop_column("provider_category")

    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.drop_constraint("job_provider_cost", type_="check")
        batch_op.drop_column("provider_cost_currency")
        batch_op.drop_column("total_provider_cost")
        batch_op.drop_column("provider_metadata")
