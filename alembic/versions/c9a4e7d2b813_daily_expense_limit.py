"""daily expense limit preference

Revision ID: c9a4e7d2b813
Revises: b1d9e4a7c205
Create Date: 2026-11-11 12:00:00.000000

Adds `user_preferences.daily_expense_limit` (NULL = no limit). Days whose total
debit spend goes above it are shown in red by the UI.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9a4e7d2b813"
down_revision: str | Sequence[str] | None = "b1d9e4a7c205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("daily_expense_limit", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("user_preferences", "daily_expense_limit")
