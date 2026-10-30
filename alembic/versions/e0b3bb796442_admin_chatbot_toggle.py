"""admin flag and chatbot feature toggle

Revision ID: e0b3bb796442
Revises: deb615c9be22
Create Date: 2026-10-29 13:00:00.000000

Adds `users.is_admin` and a singleton `app_settings` row holding
`chatbot_enabled`, so the AI chatbot can be turned on/off for all end
users, with only an admin account allowed to flip it (see
app/api/deps.py's AdminUser dependency and
app/api/v1/endpoints/settings.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0b3bb796442'
down_revision: Union[str, Sequence[str], None] = 'deb615c9be22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )

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


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("app_settings")
    op.drop_column("users", "is_admin")
