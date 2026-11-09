"""Email feature: outbox, one-time tokens, verified flag

Revision ID: b1d9e4a7c205
Revises: a8c2d6e4f913
Create Date: 2026-11-09 12:00:00.000000

* email_jobs   - the outbox. Request handlers only INSERT a row here; a
                 background worker sends it (so nobody waits on Mailgun).
* email_tokens - single-use verify-email / reset-password links, stored
                 hashed (a leaked DB must not leak working links).
* users.email_verified_at - NULL until the user clicks the confirm link.
  Every account that exists when this runs is marked verified, so nobody is
  locked out by the new "verify before login" rule.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b1d9e4a7c205'
down_revision: Union[str, Sequence[str], None] = 'a8c2d6e4f913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ")
    # Grandfather everyone who already has an account.
    op.execute("UPDATE users SET email_verified_at = now() WHERE email_verified_at IS NULL")

    op.execute("""
        CREATE TABLE IF NOT EXISTS email_tokens (
            id         UUID PRIMARY KEY,
            user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose    VARCHAR(20) NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at    TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_tokens_user_purpose ON email_tokens(user_id, purpose)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS email_jobs (
            id         UUID PRIMARY KEY,
            user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind       VARCHAR(30) NOT NULL,
            payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
            status     VARCHAR(10) NOT NULL DEFAULT 'pending',
            attempts   INTEGER NOT NULL DEFAULT 0,
            run_after  TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            sent_at    TIMESTAMPTZ
        )
    """)
    # The worker's "what is due?" query.
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_jobs_due ON email_jobs(status, run_after)")

    # The chat role gets SELECT on every new table by default (see the
    # chat_readonly_role migration). These two hold token hashes and email
    # contents, so take it back. Role may not exist in every environment.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smm_chat_readonly') THEN
                REVOKE ALL ON email_tokens, email_jobs FROM smm_chat_readonly;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_jobs")
    op.execute("DROP TABLE IF EXISTS email_tokens")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verified_at")
