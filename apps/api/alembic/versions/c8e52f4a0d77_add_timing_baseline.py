"""add timing baseline

Revision ID: c8e52f4a0d77
Revises: b3f764a9c2e1
Create Date: 2026-08-29 23:02:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8e52f4a0d77"
down_revision: str | None = "b3f764a9c2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("transcriptions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "timing_ai_baseline",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("timing_version", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.create_check_constraint(
            "transcription_timing_version", "timing_version >= 1"
        )


def downgrade() -> None:
    with op.batch_alter_table("transcriptions", schema=None) as batch_op:
        batch_op.drop_constraint("transcription_timing_version", type_="check")
        batch_op.drop_column("timing_version")
        batch_op.drop_column("timing_ai_baseline")
