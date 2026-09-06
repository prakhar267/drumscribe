"""add transcription credits

Revision ID: 6e531b0eb321
Revises: c8e52f4a0d77
Create Date: 2026-09-06 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e531b0eb321"
down_revision: str | None = "c8e52f4a0d77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("free_transcription_used_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "paid_credit_balance",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "user_paid_credit_balance", "paid_credit_balance >= 0"
        )

    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("credit_source", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("credit_refunded_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "credit_purchases",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("last_webhook_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("credit_count", sa.Integer(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.CheckConstraint("credit_count > 0", name="purchase_credit_count"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkout_session_id"),
        sa.UniqueConstraint("last_webhook_id"),
        sa.UniqueConstraint("provider_payment_id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_purchase_user_idempotency"),
    )
    op.create_index("ix_credit_purchases_status", "credit_purchases", ["status"], unique=False)
    op.create_index("ix_credit_purchases_user_id", "credit_purchases", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_credit_purchases_user_id", table_name="credit_purchases")
    op.drop_index("ix_credit_purchases_status", table_name="credit_purchases")
    op.drop_table("credit_purchases")
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.drop_column("credit_refunded_at")
        batch_op.drop_column("credit_source")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("user_paid_credit_balance", type_="check")
        batch_op.drop_column("paid_credit_balance")
        batch_op.drop_column("free_transcription_used_at")
