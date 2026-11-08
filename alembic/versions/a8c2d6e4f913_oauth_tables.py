"""OAuth tables for the Claude connector / MCP server

Revision ID: a8c2d6e4f913
Revises: e5a7c3d91b02
Create Date: 2026-11-09 10:00:00.000000

oauth_clients (Claude registers itself), oauth_codes (5 minute single-use
authorization codes) and oauth_tokens (90 day access tokens, stored hashed).
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a8c2d6e4f913'
down_revision: Union[str, Sequence[str], None] = 'e5a7c3d91b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS oauth_clients (
            id            UUID PRIMARY KEY,
            client_id     VARCHAR(255) NOT NULL UNIQUE,
            client_name   VARCHAR(255) NOT NULL,
            redirect_uris JSONB NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS oauth_codes (
            id             UUID PRIMARY KEY,
            code           VARCHAR(128) NOT NULL UNIQUE,
            client_id      UUID NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
            user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            redirect_uri   TEXT NOT NULL,
            code_challenge VARCHAR(128),
            expires_at     TIMESTAMPTZ NOT NULL,
            used           BOOLEAN NOT NULL DEFAULT false,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id           UUID PRIMARY KEY,
            token_hash   VARCHAR(64) NOT NULL UNIQUE,
            client_id    UUID NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
            user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            revoked      BOOLEAN NOT NULL DEFAULT false,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at   TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_oauth_tokens_user_id ON oauth_tokens(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_tokens")
    op.execute("DROP TABLE IF EXISTS oauth_codes")
    op.execute("DROP TABLE IF EXISTS oauth_clients")
