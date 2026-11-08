"""chat readonly role

Revision ID: deb615c9be22
Revises: 330acedcd320
Create Date: 2026-10-28 19:44:38.353177

Creates the restricted DB role used by the Text-to-SQL chat feature
(PLAN.md Phase 4). This role is deliberately NOT the table owner, so the
RLS policies from the previous migration apply to it automatically
(Postgres skips RLS for table owners/superusers by default) - no FORCE ROW
LEVEL SECURITY needed. It also has no access to `users` at all, so even a
query that slips past the sqlglot/app-level guardrails cannot read
passwords.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'deb615c9be22'
down_revision: str | Sequence[str] | None = '330acedcd320'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

READONLY_ROLE = "smm_chat_readonly"
READONLY_TABLES = (
    "banks",
    "expenses",
    "expense_entries",
    "expense_entry_tags",
    "expense_entry_tag_links",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{READONLY_ROLE}') THEN
                CREATE ROLE {READONLY_ROLE} LOGIN PASSWORD '{READONLY_ROLE}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT CONNECT ON DATABASE stalk_my_money TO {READONLY_ROLE}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {READONLY_ROLE}")
    for table in READONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {READONLY_ROLE}")
    # Belt-and-suspenders: an explicit REVOKE in case this role is ever
    # granted broader privileges by a future migration or manual change.
    op.execute(f"REVOKE ALL ON users FROM {READONLY_ROLE}")
    op.execute(f"REVOKE ALL ON _migration_id_map FROM {READONLY_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {READONLY_ROLE}")


def downgrade() -> None:
    """Downgrade schema."""
    for table in READONLY_TABLES:
        op.execute(f"REVOKE SELECT ON {table} FROM {READONLY_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {READONLY_ROLE}")
    op.execute(f"REVOKE CONNECT ON DATABASE stalk_my_money FROM {READONLY_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {READONLY_ROLE}")
