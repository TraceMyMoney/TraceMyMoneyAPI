"""initial schema

Revision ID: 330acedcd320
Revises:
Create Date: 2026-10-28 18:11:29.588497

Written by hand against app/db/tables.py (no live Postgres was reachable in
this environment to run --autogenerate; verify with `alembic upgrade head`
once Postgres is available). See PLAN.md for the schema rationale.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '330acedcd320'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False, unique=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password", sa.Text(), nullable=False),
        sa.Column("is_subscribed_to_emails", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "banks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(20), nullable=False),
        sa.Column("initial_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("current_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_disbursed_till_now", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_banks_user_id", "banks", ["user_id"])

    op.create_table(
        "expense_entry_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="uq_expense_entry_tags_user_name"),
    )

    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bank_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("banks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bank_name", sa.Text(), nullable=False),
        sa.Column("day", sa.Text(), nullable=False),
        sa.Column("expense_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("remaining_amount_till_now", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("bank_id", "user_id", "created_at", name="uq_expenses_bank_user_created_at"),
    )
    op.create_index("ix_expenses_user_id", "expenses", ["user_id"])
    op.create_index("ix_expenses_bank_id", "expenses", ["bank_id"])

    op.create_table(
        "expense_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ee_id", sa.Text(), nullable=False, unique=True),
        sa.Column("expense_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("expense_entry_type", sa.Text(), nullable=False, server_default="expense"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_expense_entries_expense_id", "expense_entries", ["expense_id"])

    op.create_table(
        "expense_entry_tag_links",
        sa.Column("expense_entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("expense_entries.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("expense_entry_tags.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("page_size", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("is_dark_mode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("privacy_mode_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("banks_display_order", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "_migration_id_map",
        sa.Column("collection", sa.Text(), primary_key=True),
        sa.Column("old_id", sa.String(24), primary_key=True),
        sa.Column("new_id", postgresql.UUID(as_uuid=True), nullable=False),
    )

    # Row-Level Security for the Text-to-SQL chat guardrails (PLAN.md Phase 4).
    # The LLM-facing read-only role scopes every SELECT to app.user_id via
    # `SET LOCAL`; these policies are the enforcement backstop if that ever
    # fails to be set.
    for table in ("banks", "expenses", "expense_entry_tags", "user_preferences"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_own ON {table} FOR SELECT
            USING (user_id = current_setting('app.user_id', true)::uuid)
            """
        )

    # expense_entries / expense_entry_tag_links have no user_id column of
    # their own; scope them via their parent expense / tag.
    op.execute("ALTER TABLE expense_entries ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY expense_entries_own ON expense_entries FOR SELECT
        USING (
            expense_id IN (
                SELECT id FROM expenses
                WHERE user_id = current_setting('app.user_id', true)::uuid
            )
        )
        """
    )

    op.execute("ALTER TABLE expense_entry_tag_links ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY expense_entry_tag_links_own ON expense_entry_tag_links FOR SELECT
        USING (
            tag_id IN (
                SELECT id FROM expense_entry_tags
                WHERE user_id = current_setting('app.user_id', true)::uuid
            )
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("_migration_id_map")
    op.drop_table("user_preferences")
    op.drop_table("expense_entry_tag_links")
    op.drop_table("expense_entries")
    op.drop_table("expenses")
    op.drop_table("expense_entry_tags")
    op.drop_table("banks")
    op.drop_table("users")
