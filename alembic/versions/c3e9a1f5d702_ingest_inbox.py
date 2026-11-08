"""SMS ingest: personal webhook token + pending transactions inbox

Revision ID: c3e9a1f5d702
Revises: b7d41c9e2a10
Create Date: 2026-11-08 12:00:00.000000

`ingest_tokens` holds the hashed per-user token used by the SMS-forwarding
webhook. `pending_transactions` is the "To review" inbox that parsed SMS land
in before the user confirms them into real expenses.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3e9a1f5d702"
down_revision: str | Sequence[str] | None = "b7d41c9e2a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "pending_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("txn_type", sa.String(10), nullable=False),
        sa.Column("merchant", sa.String(200)),
        sa.Column("description", sa.String(200)),
        sa.Column("txn_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_hint", sa.String(10)),
        sa.Column("bank_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("banks.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("dedupe_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "dedupe_hash", name="uq_pending_transactions_user_hash"),
    )
    op.create_index("ix_pending_transactions_user_status", "pending_transactions", ["user_id", "status"])

    # Same row-level-security backstop the other user-owned tables have.
    for table in ("ingest_tokens", "pending_transactions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_own ON {table} FOR SELECT
            USING (user_id = current_setting('app.user_id', true)::uuid)
            """
        )


def downgrade() -> None:
    op.drop_index("ix_pending_transactions_user_status", table_name="pending_transactions")
    op.drop_table("pending_transactions")
    op.drop_table("ingest_tokens")
