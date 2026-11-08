"""admin-controlled per-user login disable

Revision ID: a3c8d914fb20
Revises: f6ff3284212e
Create Date: 2026-10-29 21:35:00.000000

Adds `users.is_disabled` so an admin can lock a user out entirely (not
just revoke chatbot access) from the admin dashboard - enforced in
app/api/deps.get_current_user (kills already-issued tokens too, not just
new logins) and app/api/v1/endpoints/auth.py's login/refresh.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c8d914fb20"
down_revision: str | Sequence[str] | None = "f6ff3284212e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("is_disabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "is_disabled")
