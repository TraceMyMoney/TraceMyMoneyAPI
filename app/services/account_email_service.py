"""Signup confirmation and password reset: everything that turns an account
action into a queued email, and a clicked link back into an account change.

Nothing here talks to Mailgun. Emails are only queued (enqueue_email); the
background worker sends them.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.tables import email_jobs, users
from app.services.email import tokens
from app.services.email.outbox import KIND_RESET_PASSWORD, KIND_VERIFY_EMAIL, enqueue_email, wake_worker

# Don't queue the same kind of email for the same account more often than this.
COOLDOWN = timedelta(seconds=60)


class AccountEmailService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _find_user(self, email: str):
        return (
            (await self.db.execute(select(users).where(func.lower(users.c.email) == email.strip().lower())))
            .mappings()
            .first()
        )

    async def _recently_queued(self, user_id, kind: str) -> bool:
        since = datetime.now(timezone.utc) - COOLDOWN
        row = (
            await self.db.execute(
                select(email_jobs.c.id)
                .where(email_jobs.c.user_id == user_id, email_jobs.c.kind == kind, email_jobs.c.created_at > since)
                .limit(1)
            )
        ).first()
        return row is not None

    async def _queue_link_email(self, user_id, kind: str, purpose: str, ttl: timedelta) -> None:
        raw = await tokens.create_token(self.db, user_id, purpose, ttl)
        await enqueue_email(self.db, user_id, kind, {"token": raw}, commit=False)
        await self.db.commit()  # token + job together, or neither
        wake_worker()

    # ---- signup confirmation -------------------------------------------------

    async def start_verification(self, user_id: str | uuid.UUID) -> None:
        """Queue the confirm-your-email message (called right after signup)."""
        await self._queue_link_email(uuid.UUID(str(user_id)), KIND_VERIFY_EMAIL, tokens.PURPOSE_VERIFY, tokens.VERIFY_TTL)

    async def resend_verification(self, email: str) -> None:
        """Silently does nothing for unknown, already-verified, disabled or
        recently-mailed accounts, so the endpoint never reveals which emails exist."""
        user = await self._find_user(email)
        if not user or user["email_verified_at"] is not None or user["is_disabled"]:
            return
        if await self._recently_queued(user["id"], KIND_VERIFY_EMAIL):
            return
        await self._queue_link_email(user["id"], KIND_VERIFY_EMAIL, tokens.PURPOSE_VERIFY, tokens.VERIFY_TTL)

    async def verify(self, raw_token: str) -> bool:
        """Mark the account verified. A link that was already used for a verified
        account still counts as success (double clicks, browser retries)."""
        user_id = await tokens.consume_token(self.db, raw_token, tokens.PURPOSE_VERIFY)
        if user_id is None:
            earlier = await tokens.was_already_used(self.db, raw_token, tokens.PURPOSE_VERIFY)
            if earlier is None:
                return False
            row = (await self.db.execute(select(users.c.email_verified_at).where(users.c.id == earlier))).first()
            return bool(row and row[0] is not None)
        await self.db.execute(
            users.update()
            .where(users.c.id == user_id, users.c.email_verified_at.is_(None))
            .values(email_verified_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return True

    # ---- password reset ------------------------------------------------------

    async def request_password_reset(self, email: str) -> None:
        """Queue a reset link if the account exists. Same silent no-op rules as above."""
        user = await self._find_user(email)
        if not user or user["is_disabled"]:
            return
        if await self._recently_queued(user["id"], KIND_RESET_PASSWORD):
            return
        await self._queue_link_email(user["id"], KIND_RESET_PASSWORD, tokens.PURPOSE_RESET, tokens.RESET_TTL)

    async def reset_password(self, raw_token: str, new_password: str) -> bool:
        user_id = await tokens.consume_token(self.db, raw_token, tokens.PURPOSE_RESET)
        if user_id is None:
            return False
        now = datetime.now(timezone.utc)
        # Following an emailed link also proves the inbox is theirs, so an
        # unverified account is verified by a successful reset.
        await self.db.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(
                password=get_password_hash(new_password),
                email_verified_at=func.coalesce(users.c.email_verified_at, now),
                updated_at=now,
            )
        )
        await self.db.commit()
        return True
