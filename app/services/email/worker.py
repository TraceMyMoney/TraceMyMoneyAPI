"""Background worker for the email outbox.

Runs inside the API process (started from main.py's lifespan). It claims due
jobs with FOR UPDATE SKIP LOCKED, so two workers (or two containers) never
send the same email, sends them through Mailgun, and:

* success                  -> status "sent", payload scrubbed (it may hold a raw token)
* temporary failure        -> back to "pending" with a growing delay (1m, 5m, 30m, 2h)
* permanent failure, or the 5th failed attempt -> status "failed", error kept
* a crash mid-send         -> the claim is a 5-minute lease; once it lapses the job is
                              picked up again, so a restart never loses an email
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.tables import email_jobs, users
from app.services.email import outbox
from app.services.email.jobs import UnknownJobKind, build_message
from app.services.email.sender import EmailSendError, send_email

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_DELAYS = [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2)]
LEASE = timedelta(minutes=5)
BATCH_SIZE = 10
POLL_SECONDS = 5.0

_CLAIM_SQL = text(
    """
    UPDATE email_jobs
       SET status = 'sending',
           attempts = attempts + 1,
           run_after = :lease_until
     WHERE id IN (
            SELECT id FROM email_jobs
             WHERE status IN ('pending', 'sending') AND run_after <= :now
             ORDER BY run_after
             LIMIT :limit
               FOR UPDATE SKIP LOCKED
     )
 RETURNING id, user_id, kind, payload, attempts
    """
)


def _retry_delay(attempts: int) -> timedelta:
    return RETRY_DELAYS[min(attempts - 1, len(RETRY_DELAYS) - 1)]


async def _claim(db: AsyncSession) -> list[dict]:
    now = datetime.now(timezone.utc)
    result = await db.execute(_CLAIM_SQL, {"now": now, "lease_until": now + LEASE, "limit": BATCH_SIZE})
    rows = [dict(r) for r in result.mappings().all()]
    for r in rows:
        if isinstance(r["payload"], str):  # raw SQL may hand JSONB back as text
            r["payload"] = json.loads(r["payload"])
    await db.commit()
    return rows


async def _finish(db: AsyncSession, job_id, **values) -> None:
    await db.execute(email_jobs.update().where(email_jobs.c.id == job_id).values(**values))
    await db.commit()


async def _process(db: AsyncSession, job: dict) -> None:
    job_id, attempts = job["id"], job["attempts"]
    try:
        row = (await db.execute(select(users.c.email).where(users.c.id == job["user_id"]))).first()
        if row is None:
            await _finish(db, job_id, status="failed", last_error="user no longer exists", payload={})
            return
        message = await build_message(db, job, row[0])
        await send_email(message)
    except EmailSendError as e:
        await _record_failure(db, job_id, attempts, str(e), permanent=e.permanent)
        return
    except UnknownJobKind as e:  # retrying cannot fix a missing builder
        await _record_failure(db, job_id, attempts, str(e), permanent=True)
        return
    except Exception as e:  # a bug in a builder must not kill the worker or retry forever
        logger.exception("Email job %s (%s) crashed while building/sending", job_id, job["kind"])
        await _record_failure(db, job_id, attempts, f"{type(e).__name__}: {e}", permanent=False)
        return
    await _finish(db, job_id, status="sent", sent_at=datetime.now(timezone.utc), last_error=None, payload={})
    logger.info("Email job %s (%s) sent", job_id, job["kind"])


async def _record_failure(db: AsyncSession, job_id, attempts: int, error: str, permanent: bool) -> None:
    if permanent or attempts >= MAX_ATTEMPTS:
        logger.error("Email job %s failed for good after %d attempt(s): %s", job_id, attempts, error)
        await _finish(db, job_id, status="failed", last_error=error[:500], payload={})
    else:
        delay = _retry_delay(attempts)
        logger.warning("Email job %s failed (attempt %d), retrying in %s: %s", job_id, attempts, delay, error)
        await _finish(
            db,
            job_id,
            status="pending",
            last_error=error[:500],
            run_after=datetime.now(timezone.utc) + delay,
        )


async def run_once(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Claim and process one batch of due jobs. Returns how many were handled."""
    async with session_factory() as db:
        jobs = await _claim(db)
    for job in jobs:
        # Own session per job so one failure can't poison the next.
        async with session_factory() as db:
            await _process(db, job)
    return len(jobs)


async def worker_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Poll forever; woken instantly when a job is enqueued in this process."""
    wake = asyncio.Event()
    outbox.set_wake_event(wake)
    logger.info("Email worker started")
    try:
        while True:
            try:
                handled = await run_once(session_factory)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Email worker iteration failed")
                handled = 0
            if handled == BATCH_SIZE:
                continue  # more may be waiting
            try:
                await asyncio.wait_for(wake.wait(), timeout=POLL_SECONDS)
            except asyncio.TimeoutError:
                pass
            wake.clear()
    finally:
        outbox.set_wake_event(None)
        logger.info("Email worker stopped")
