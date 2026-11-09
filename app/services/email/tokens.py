"""One-time email links (verify-email, reset-password).

The raw token is a random 256-bit string that only ever travels in the email.
The database keeps just its sha256 hash, so a leaked table cannot be turned
into working links. Tokens expire and work once.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import email_tokens

PURPOSE_VERIFY = "verify"
PURPOSE_RESET = "reset"

VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_token(db: AsyncSession, user_id: str | uuid.UUID, purpose: str, ttl: timedelta) -> str:
    """Make a fresh token for the user and retire their older unused ones of the
    same purpose (a new "forgot password" request cancels the previous link).
    Does not commit: the caller commits it together with the queued email."""
    uid = uuid.UUID(str(user_id))
    now = datetime.now(timezone.utc)
    await db.execute(
        text("UPDATE email_tokens SET used_at = :now WHERE user_id = :uid AND purpose = :p AND used_at IS NULL"),
        {"now": now, "uid": uid, "p": purpose},
    )
    raw = secrets.token_urlsafe(32)
    await db.execute(
        email_tokens.insert().values(
            id=uuid.uuid4(), user_id=uid, purpose=purpose, token_hash=hash_token(raw), expires_at=now + ttl
        )
    )
    return raw


async def consume_token(db: AsyncSession, raw: str, purpose: str) -> uuid.UUID | None:
    """Atomically use a token. Returns the user id, or None if it is unknown,
    expired, already used, or for a different purpose. Does not commit."""
    row = (
        await db.execute(
            text(
                """
                UPDATE email_tokens SET used_at = :now
                 WHERE token_hash = :h AND purpose = :p AND used_at IS NULL AND expires_at > :now
             RETURNING user_id
                """
            ),
            {"now": datetime.now(timezone.utc), "h": hash_token(raw), "p": purpose},
        )
    ).first()
    return row[0] if row else None


async def was_already_used(db: AsyncSession, raw: str, purpose: str) -> uuid.UUID | None:
    """The user id behind a token that exists but was already used (not expired
    check on purpose: used tokens are only consulted to be friendly to a
    double-clicked verify link)."""
    row = (
        await db.execute(
            select(email_tokens.c.user_id).where(
                email_tokens.c.token_hash == hash_token(raw),
                email_tokens.c.purpose == purpose,
                email_tokens.c.used_at.is_not(None),
            )
        )
    ).first()
    return row[0] if row else None
