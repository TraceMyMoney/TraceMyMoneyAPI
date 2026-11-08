"""
SQLAlchemy Core table definitions for the PostgreSQL migration target.
Mirrors the schema in PLAN.md. Kept separate from app/models/ (the Pydantic
models mirroring Mongo documents) per the layering convention in CLAUDE.md.
"""

import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()


def uuid_pk():
    return Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


users = Table(
    "users",
    metadata,
    uuid_pk(),
    Column("username", Text, nullable=False, unique=True),
    Column("email", Text, nullable=False, unique=True),
    Column("password", Text, nullable=False),
    Column("is_subscribed_to_emails", Boolean, nullable=False, server_default="true"),
    Column("is_admin", Boolean, nullable=False, server_default="false"),
    Column("chatbot_enabled", Boolean, nullable=False, server_default="false"),
    Column("is_disabled", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

banks = Table(
    "banks",
    metadata,
    uuid_pk(),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(20), nullable=False),
    Column("initial_balance", Numeric(18, 2), nullable=False, server_default="0"),
    Column("current_balance", Numeric(18, 2), nullable=False, server_default="0"),
    Column("total_disbursed_till_now", Numeric(18, 2), nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

expense_entry_tags = Table(
    "expense_entry_tags",
    metadata,
    uuid_pk(),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(50), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "name", name="uq_expense_entry_tags_user_name"),
)

expenses = Table(
    "expenses",
    metadata,
    uuid_pk(),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("bank_id", UUID(as_uuid=True), ForeignKey("banks.id", ondelete="CASCADE"), nullable=False),
    Column("bank_name", Text, nullable=False),
    Column("day", Text, nullable=False),
    Column("expense_total", Numeric(18, 2), nullable=False, server_default="0"),
    Column("remaining_amount_till_now", Numeric(18, 2), nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("bank_id", "user_id", "created_at", name="uq_expenses_bank_user_created_at"),
)

expense_entries = Table(
    "expense_entries",
    metadata,
    uuid_pk(),
    Column("ee_id", Text, nullable=False, unique=True),
    Column("expense_id", UUID(as_uuid=True), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("expense_entry_type", Text, nullable=False, server_default="expense"),
    Column("position", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

expense_entry_tag_links = Table(
    "expense_entry_tag_links",
    metadata,
    Column(
        "expense_entry_id",
        UUID(as_uuid=True),
        ForeignKey("expense_entries.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("expense_entry_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# Personal webhook token for the SMS-forwarding automation (iPhone Shortcuts
# etc.), which can't do the JWT login/refresh dance. Only the sha256 of the
# token is stored; the plaintext is shown once, when it is created.
ingest_tokens = Table(
    "ingest_tokens",
    metadata,
    uuid_pk(),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_used_at", DateTime(timezone=True)),
)

# Transactions parsed from forwarded bank SMS, waiting for the user to
# confirm them. Nothing is written to `expenses` until confirmation.
pending_transactions = Table(
    "pending_transactions",
    metadata,
    uuid_pk(),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("raw_text", Text, nullable=False),
    Column("amount", Numeric(18, 2), nullable=False),
    Column("txn_type", String(10), nullable=False),  # "debit" | "credit"
    Column("merchant", String(200)),
    Column("description", String(200)),
    Column("txn_date", DateTime(timezone=True), nullable=False),
    Column("account_hint", String(10)),
    Column("bank_id", UUID(as_uuid=True), ForeignKey("banks.id", ondelete="SET NULL")),
    Column("status", String(12), nullable=False, server_default="pending"),  # pending | confirmed | rejected
    Column("dedupe_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "dedupe_hash", name="uq_pending_transactions_user_hash"),
)

user_preferences = Table(
    "user_preferences",
    metadata,
    uuid_pk(),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("page_size", Integer, nullable=False, server_default="5"),
    Column("is_dark_mode", Boolean, nullable=False, server_default="false"),
    Column("privacy_mode_enabled", Boolean, nullable=False, server_default="false"),
    Column("banks_display_order", ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"),
    Column("default_excluded_tags", ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# Generic admin-editable key/value settings store (active LLM provider/
# model, feature flags, etc.) - see app/services/app_settings_service.py.
# A handful of named keys, not a per-row-per-setting table, since each
# setting is really a small JSON object (e.g. ai_config bundles provider +
# model + generation params together) read/written as a unit.
app_settings = Table(
    "app_settings",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
)

_migration_id_map = Table(
    "_migration_id_map",
    metadata,
    Column("collection", Text, primary_key=True),
    Column("old_id", String(24), primary_key=True),
    Column("new_id", UUID(as_uuid=True), nullable=False),
)
