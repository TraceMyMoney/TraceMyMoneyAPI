"""SMS ingest: per-user auto-add switch

Revision ID: d4f2b8c61a93
Revises: c3e9a1f5d702
Create Date: 2026-11-08 18:00:00.000000

`ingest_tokens.auto_add`: when true (default), a forwarded SMS that clearly
names one of the user's accounts is added to expenses straight away instead
of waiting in the review list.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4f2b8c61a93"
down_revision: str | Sequence[str] | None = "c3e9a1f5d702"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingest_tokens",
        sa.Column("auto_add", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("ingest_tokens", "auto_add")
