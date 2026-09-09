"""harden freemium billing

Revision ID: 9f4b8d16a2c7
Revises: 6e531b0eb321
Create Date: 2026-09-10 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9f4b8d16a2c7"
down_revision: str | None = "6e531b0eb321"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "free_transcription_claims",
        sa.Column("identity_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("identity_hash"),
    )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("free_transcription_claim_hash", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            "ix_users_free_transcription_claim_hash",
            ["free_transcription_claim_hash"],
            unique=False,
        )

    with op.batch_alter_table("credit_purchases", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("remaining_credit_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("revoked_credit_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("provider_refund_id", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint(
            "uq_credit_purchases_provider_refund_id", ["provider_refund_id"]
        )
        batch_op.create_check_constraint(
            "purchase_remaining_credits",
            "remaining_credit_count >= 0 AND remaining_credit_count <= credit_count",
        )
        batch_op.create_check_constraint(
            "purchase_revoked_credits",
            "revoked_credit_count >= 0 AND revoked_credit_count <= credit_count",
        )

    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("credit_purchase_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_processing_jobs_credit_purchase_id",
            "credit_purchases",
            ["credit_purchase_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_processing_jobs_credit_purchase_id", ["credit_purchase_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_processing_jobs_credit_purchase_id")
        batch_op.drop_constraint("fk_processing_jobs_credit_purchase_id", type_="foreignkey")
        batch_op.drop_column("credit_purchase_id")

    with op.batch_alter_table("credit_purchases", schema=None) as batch_op:
        batch_op.drop_constraint("purchase_revoked_credits", type_="check")
        batch_op.drop_constraint("purchase_remaining_credits", type_="check")
        batch_op.drop_constraint("uq_credit_purchases_provider_refund_id", type_="unique")
        batch_op.drop_column("provider_refund_id")
        batch_op.drop_column("revoked_credit_count")
        batch_op.drop_column("remaining_credit_count")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_free_transcription_claim_hash")
        batch_op.drop_column("free_transcription_claim_hash")

    op.drop_table("free_transcription_claims")
