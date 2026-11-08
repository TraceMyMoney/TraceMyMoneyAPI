"""SMS ingest: allow the same SMS text to be recorded more than once

Revision ID: e5a7c3d91b02
Revises: d4f2b8c61a93
Create Date: 2026-11-08 20:00:00.000000

Every forwarded SMS now creates an expense (or review item), even if its text
is identical to an earlier one, so the unique (user_id, dedupe_hash)
constraint goes away and becomes a plain index.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e5a7c3d91b02'
down_revision: Union[str, Sequence[str], None] = 'd4f2b8c61a93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_pending_transactions_user_hash", "pending_transactions", type_="unique")
    op.create_index("ix_pending_transactions_user_hash", "pending_transactions", ["user_id", "dedupe_hash"])


def downgrade() -> None:
    op.drop_index("ix_pending_transactions_user_hash", table_name="pending_transactions")
    op.create_unique_constraint("uq_pending_transactions_user_hash", "pending_transactions", ["user_id", "dedupe_hash"])
