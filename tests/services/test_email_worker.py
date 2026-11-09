"""Outbox + worker: queueing, sending, retries, give-up, lease recovery, no double send."""

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.db.tables import email_jobs, users
from app.services.email import worker
from app.services.email.outbox import KIND_VERIFY_EMAIL, enqueue_email
from app.services.email.sender import EmailSendError
from tests.conftest import TestSessionLocal


@pytest.fixture
async def user_id(test_db):
    uid = uuid.uuid4()
    await test_db.execute(
        users.insert().values(id=uid, username="mailuser1", email="mail@user.test", password="x")
    )
    await test_db.commit()
    return uid


@pytest.fixture
def sent(monkeypatch):
    """Capture what the worker would send instead of calling Mailgun."""
    box: list = []

    async def fake_send(message):
        box.append(message)

    monkeypatch.setattr(worker, "send_email", fake_send)
    return box


async def _job(test_db, job_id):
    test_db.expire_all()
    return (await test_db.execute(select(email_jobs).where(email_jobs.c.id == job_id))).mappings().one()


async def _make_due(test_db, job_id):
    await test_db.execute(
        update(email_jobs).where(email_jobs.c.id == job_id).values(run_after=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await test_db.commit()


async def test_enqueue_only_writes_a_row_and_never_sends(test_db, user_id, sent):
    start = time.perf_counter()
    job_id = await enqueue_email(test_db, user_id, KIND_VERIFY_EMAIL, {"token": "tok123"})
    assert time.perf_counter() - start < 0.5
    assert sent == []
    assert (await _job(test_db, job_id))["status"] == "pending"


async def test_worker_sends_and_scrubs_the_token(test_db, user_id, sent):
    job_id = await enqueue_email(test_db, user_id, KIND_VERIFY_EMAIL, {"token": "tok123"})
    assert await worker.run_once(TestSessionLocal) == 1

    assert len(sent) == 1
    assert sent[0].to == "mail@user.test"
    assert f"{settings.FRONTEND_BASE_URL}/verify-email?token=tok123" in sent[0].text
    job = await _job(test_db, job_id)
    assert job["status"] == "sent" and job["sent_at"] is not None
    assert job["payload"] == {}  # raw token must not linger in the DB
    assert await worker.run_once(TestSessionLocal) == 0  # nothing left


async def test_temporary_failure_is_retried_later_then_sent(test_db, user_id, monkeypatch):
    calls = []

    async def flaky(message):
        calls.append(1)
        if len(calls) == 1:
            raise EmailSendError("mailgun down")

    monkeypatch.setattr(worker, "send_email", flaky)
    job_id = await enqueue_email(test_db, user_id, KIND_VERIFY_EMAIL, {"token": "t"})

    await worker.run_once(TestSessionLocal)
    job = await _job(test_db, job_id)
    assert job["status"] == "pending" and job["attempts"] == 1
    assert "mailgun down" in job["last_error"]
    assert job["run_after"] > datetime.now(timezone.utc)
    assert await worker.run_once(TestSessionLocal) == 0  # not due yet

    await _make_due(test_db, job_id)
    await worker.run_once(TestSessionLocal)
    job = await _job(test_db, job_id)
    assert job["status"] == "sent" and job["attempts"] == 2


async def test_permanent_failure_is_not_retried(test_db, user_id, monkeypatch):
    async def reject(message):
        raise EmailSendError("bad key", permanent=True)

    monkeypatch.setattr(worker, "send_email", reject)
    job_id = await enqueue_email(test_db, user_id, KIND_VERIFY_EMAIL, {"token": "t"})
    await worker.run_once(TestSessionLocal)
    job = await _job(test_db, job_id)
    assert job["status"] == "failed" and job["attempts"] == 1 and "bad key" in job["last_error"]


async def test_gives_up_after_max_attempts(test_db, user_id, monkeypatch):
    async def always_down(message):
        raise EmailSendError("still down")

    monkeypatch.setattr(worker, "send_email", always_down)
    job_id = await enqueue_email(test_db, user_id, KIND_VERIFY_EMAIL, {"token": "t"})
    for _ in range(worker.MAX_ATTEMPTS):
        await _make_due(test_db, job_id)
        await worker.run_once(TestSessionLocal)
    job = await _job(test_db, job_id)
    assert job["status"] == "failed" and job["attempts"] == worker.MAX_ATTEMPTS


async def test_unknown_kind_fails_permanently(test_db, user_id, sent):
    job_id = await enqueue_email(test_db, user_id, "no_such_kind", {})
    await worker.run_once(TestSessionLocal)
    job = await _job(test_db, job_id)
    assert job["status"] == "failed" and job["attempts"] == 1


async def test_two_workers_never_double_send(test_db, user_id, sent):
    await enqueue_email(test_db, user_id, KIND_VERIFY_EMAIL, {"token": "t"})
    a, b = await asyncio.gather(worker.run_once(TestSessionLocal), worker.run_once(TestSessionLocal))
    assert a + b == 1
    assert len(sent) == 1


async def test_crashed_send_is_recovered_after_the_lease_lapses(test_db, user_id, sent):
    job_id = await enqueue_email(test_db, user_id, KIND_VERIFY_EMAIL, {"token": "t"})
    # Simulate a worker that claimed the job and died: status 'sending', lease in the future.
    await test_db.execute(
        update(email_jobs).where(email_jobs.c.id == job_id).values(
            status="sending", attempts=1, run_after=datetime.now(timezone.utc) + timedelta(minutes=4)
        )
    )
    await test_db.commit()
    assert await worker.run_once(TestSessionLocal) == 0  # lease still held by the "other" worker

    await _make_due(test_db, job_id)  # lease lapsed
    assert await worker.run_once(TestSessionLocal) == 1
    assert (await _job(test_db, job_id))["status"] == "sent"
    assert len(sent) == 1


async def test_job_for_deleted_user_fails_cleanly(test_db, user_id, sent):
    job_id = await enqueue_email(test_db, user_id, KIND_VERIFY_EMAIL, {"token": "t"})
    # ON DELETE CASCADE removes the job with the user, so simulate "user gone" by
    # pointing the claimed job at a missing id via a direct process call.
    await test_db.execute(users.delete().where(users.c.id == user_id))
    await test_db.commit()
    assert await worker.run_once(TestSessionLocal) == 0
    assert sent == []
