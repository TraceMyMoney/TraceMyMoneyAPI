"""generic admin-editable key/value app_settings store

Revision ID: f6ff3284212e
Revises: 0af3fa190666
Create Date: 2026-10-29 21:30:00.000000

Reintroduces `app_settings` (the prior singleton-row version was dropped
in 0af3fa190666) as a generic key/value store: one row per named setting,
value as JSONB. Backs the admin dashboard's AI-provider config and
feature flags - see app/services/app_settings_service.py. Unlike the old
table, this isn't a singleton; `key` is the primary key and each row is a
self-contained JSON blob (e.g. `ai_config`, `feature_flags`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f6ff3284212e'
down_revision: Union[str, Sequence[str], None] = '0af3fa190666'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("app_settings")
