"""per-user chatbot access (replaces the global toggle)

Revision ID: 0af3fa190666
Revises: e0b3bb796442
Create Date: 2026-10-29 14:00:00.000000

The previous migration gave the chatbot a single app-wide on/off switch.
That's the wrong shape for what this is actually meant to be - a
per-user, admin-granted entitlement (think "paid feature"), with an admin
dashboard listing every user so access can be granted/revoked
individually. Drops `app_settings` and adds `users.chatbot_enabled`
instead.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0af3fa190666'
down_revision: str | Sequence[str] | None = 'e0b3bb796442'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("chatbot_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.drop_table("app_settings")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chatbot_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id = 1", name="ck_app_settings_singleton"),
    )
    op.execute("INSERT INTO app_settings (id, chatbot_enabled) VALUES (1, false)")
    op.drop_column("users", "chatbot_enabled")
