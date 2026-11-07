"""per-user default excluded tags

Revision ID: b7d41c9e2a10
Revises: a3c8d914fb20
Create Date: 2026-11-06 12:00:00.000000

Adds `user_preferences.default_excluded_tags`: tag ids whose entries are
hidden from the expense list by default (the UI still lets the user change
the exclusion per session).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7d41c9e2a10"
down_revision: str | Sequence[str] | None = "a3c8d914fb20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column(
            "default_excluded_tags",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "default_excluded_tags")
