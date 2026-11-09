"""The email outbox: request handlers call enqueue_email() and return.

enqueue_email only INSERTs a row into email_jobs (a few milliseconds). The
background worker (worker.py) sends it. Nothing in a request ever talks to
Mailgun, so a slow or broken mail server can never make a user wait.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import email_jobs

# Job kinds (email_jobs.kind).
KIND_VERIFY_EMAIL = "verify_email"
KIND_RESET_PASSWORD = "reset_password"
KIND_EXPENSE_REPORT = "expense_report"

# Set by the running worker so a new job is picked up immediately instead of
# waiting for the next poll. None when no worker runs (tests, other processes):
# the poll still finds the job, just a few seconds later.
_wake_event: asyncio.Event | None = None


def set_wake_event(event: asyncio.Event | None) -> None:
    global _wake_event
    _wake_event = event


def wake_worker() -> None:
    if _wake_event is not None:
        _wake_event.set()


async def enqueue_email(
    db: AsyncSession,
    user_id: str | uuid.UUID,
    kind: str,
    payload: dict | None = None,
    *,
    commit: bool = True,
) -> uuid.UUID:
    """Queue one email for `user_id` and return the job id.

    `commit=False` lets the caller put the job in the same transaction as
    something else (e.g. the token row), so both exist or neither does.
    """
    job_id = uuid.uuid4()
    await db.execute(
        email_jobs.insert().values(
            id=job_id,
            user_id=uuid.UUID(str(user_id)),
            kind=kind,
            payload=payload or {},
            status="pending",
            run_after=datetime.now(timezone.utc),
        )
    )
    if commit:
        await db.commit()
        wake_worker()
    return job_id
