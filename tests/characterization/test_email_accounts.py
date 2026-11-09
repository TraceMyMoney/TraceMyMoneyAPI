"""Signup confirmation + password reset, end to end through the API.

Emails are never sent: the worker is run by hand with send_email replaced, and
the raw token is read from the queued job (the only place it exists besides the
email itself)."""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.core.rate_limit import reset_rate_limits
from app.db.tables import email_jobs, email_tokens, users
from app.services.email import worker
from tests.conftest import TestSessionLocal

CREDS = {"username": "newuser123", "email": "new.user@example.com", "password": "password123"}


@pytest.fixture(autouse=True)
def _fresh_limits():
    reset_rate_limits()


@pytest.fixture
def sent(monkeypatch):
    box = []

    async def fake_send(message):
        box.append(message)

    monkeypatch.setattr(worker, "send_email", fake_send)
    return box


def _token_from(message) -> str:
    return message.text.split("token=")[1].split()[0].strip()


async def _register(client, **over):
    return await client.post("/register", json={**CREDS, **over})


async def test_register_queues_email_without_sending_inline(client, test_db, sent):
    start = time.perf_counter()
    resp = await _register(client)
    assert resp.status_code == 200
    assert time.perf_counter() - start < 2
    assert sent == []  # the request itself never sends
    jobs = (await test_db.execute(select(email_jobs))).mappings().all()
    assert len(jobs) == 1 and jobs[0]["kind"] == "verify_email" and jobs[0]["status"] == "pending"


async def test_signup_to_login_flow(client, test_db, sent):
    await _register(client)

    # Not verified yet: login refused with a message the UI can recognise.
    resp = await client.post("/login", json={"username": CREDS["username"], "password": CREDS["password"]})
    assert resp.status_code == 403 and resp.json()["detail"].startswith("Email not verified")

    await worker.run_once(TestSessionLocal)
    assert len(sent) == 1 and sent[0].to == CREDS["email"]
    token = _token_from(sent[0])

    assert (await client.post("/verify-email", json={"token": token})).status_code == 200
    # Clicking the same link again (double click) is still a success.
    assert (await client.post("/verify-email", json={"token": token})).status_code == 200

    resp = await client.post("/login", json={"username": CREDS["username"], "password": CREDS["password"]})
    assert resp.status_code == 200 and resp.json()["token"]


async def test_bad_or_expired_verify_token_rejected(client, test_db, sent):
    assert (await client.post("/verify-email", json={"token": "nonsense"})).status_code == 400

    await _register(client)
    await worker.run_once(TestSessionLocal)
    token = _token_from(sent[0])
    await test_db.execute(text("UPDATE email_tokens SET expires_at = now() - interval '1 minute'"))
    await test_db.commit()
    assert (await client.post("/verify-email", json={"token": token})).status_code == 400


async def test_only_the_hash_of_a_token_is_stored(client, test_db, sent):
    await _register(client)
    await worker.run_once(TestSessionLocal)
    token = _token_from(sent[0])
    stored = (await test_db.execute(select(email_tokens.c.token_hash))).scalars().all()
    assert stored and token not in stored


async def test_resend_verification_and_cooldown(client, test_db, sent):
    await _register(client)
    await worker.run_once(TestSessionLocal)
    first = _token_from(sent[0])

    # Inside the cooldown nothing new is queued, but the answer is identical.
    r = await client.post("/resend-verification", json={"email": CREDS["email"]})
    assert r.status_code == 200
    assert (await test_db.execute(select(email_jobs).where(email_jobs.c.status == "pending"))).first() is None

    # After the cooldown a new link is sent and the old one stops working.
    await test_db.execute(text("UPDATE email_jobs SET created_at = now() - interval '5 minutes'"))
    await test_db.commit()
    await client.post("/resend-verification", json={"email": CREDS["email"]})
    await worker.run_once(TestSessionLocal)
    assert len(sent) == 2
    second = _token_from(sent[1])
    assert second != first
    assert (await client.post("/verify-email", json={"token": first})).status_code == 400
    assert (await client.post("/verify-email", json={"token": second})).status_code == 200


async def test_resend_for_unknown_email_looks_identical_and_sends_nothing(client, test_db, sent):
    known = await client.post("/resend-verification", json={"email": "ghost@nowhere.test"})
    await _register(client)
    real = await client.post("/resend-verification", json={"email": CREDS["email"]})
    assert known.status_code == real.status_code == 200 and known.json() == real.json()
    await worker.run_once(TestSessionLocal)
    assert all(m.to != "ghost@nowhere.test" for m in sent)


async def _verified_user(client, test_db):
    await _register(client)
    await test_db.execute(text("UPDATE users SET email_verified_at = now()"))
    await test_db.commit()


async def test_password_reset_flow(client, test_db, sent):
    await _verified_user(client, test_db)
    r = await client.post("/forgot-password", json={"email": CREDS["email"]})
    assert r.status_code == 200
    await worker.run_once(TestSessionLocal)
    reset_mail = [m for m in sent if "reset-password" in m.text][0]
    token = _token_from(reset_mail)

    r = await client.post("/reset-password", json={"token": token, "password": "brandnewpass1"})
    assert r.status_code == 200
    # Works once only.
    assert (await client.post("/reset-password", json={"token": token, "password": "anotherpass12"})).status_code == 400

    assert (await client.post("/login", json={"username": CREDS["username"], "password": CREDS["password"]})).status_code == 400
    assert (await client.post("/login", json={"username": CREDS["username"], "password": "brandnewpass1"})).status_code == 200


async def test_forgot_password_does_not_reveal_whether_email_exists(client, test_db, sent):
    await _verified_user(client, test_db)
    a = await client.post("/forgot-password", json={"email": "ghost@nowhere.test"})
    b = await client.post("/forgot-password", json={"email": CREDS["email"]})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    await worker.run_once(TestSessionLocal)
    assert [m.to for m in sent if "reset-password" in m.text] == [CREDS["email"]]


async def test_new_reset_request_cancels_the_old_link(client, test_db, sent):
    await _verified_user(client, test_db)
    await client.post("/forgot-password", json={"email": CREDS["email"]})
    await worker.run_once(TestSessionLocal)
    old = _token_from([m for m in sent if "reset-password" in m.text][0])

    await test_db.execute(text("UPDATE email_jobs SET created_at = now() - interval '5 minutes'"))
    await test_db.commit()
    await client.post("/forgot-password", json={"email": CREDS["email"]})
    await worker.run_once(TestSessionLocal)
    new = _token_from([m for m in sent if "reset-password" in m.text][-1])

    assert (await client.post("/reset-password", json={"token": old, "password": "brandnewpass1"})).status_code == 400
    assert (await client.post("/reset-password", json={"token": new, "password": "brandnewpass1"})).status_code == 200


async def test_expired_reset_token_and_short_password_rejected(client, test_db, sent):
    await _verified_user(client, test_db)
    await client.post("/forgot-password", json={"email": CREDS["email"]})
    await worker.run_once(TestSessionLocal)
    token = _token_from([m for m in sent if "reset-password" in m.text][0])

    assert (await client.post("/reset-password", json={"token": token, "password": "short"})).status_code == 400
    await test_db.execute(text("UPDATE email_tokens SET expires_at = now() - interval '1 minute' WHERE purpose = 'reset'"))
    await test_db.commit()
    assert (await client.post("/reset-password", json={"token": token, "password": "brandnewpass1"})).status_code == 400


async def test_disabled_account_gets_no_reset_email(client, test_db, sent):
    await _verified_user(client, test_db)
    await worker.run_once(TestSessionLocal)  # flush the signup email
    sent.clear()
    await test_db.execute(text("UPDATE email_jobs SET created_at = now() - interval '5 minutes'"))
    await test_db.execute(text("UPDATE users SET is_disabled = true"))
    await test_db.commit()
    await client.post("/forgot-password", json={"email": CREDS["email"]})
    await worker.run_once(TestSessionLocal)
    assert sent == []


async def test_reset_also_verifies_an_unverified_account(client, test_db, sent):
    await _register(client)
    await worker.run_once(TestSessionLocal)  # sends the verify mail, ignore it
    sent.clear()
    await test_db.execute(text("UPDATE email_jobs SET created_at = now() - interval '5 minutes'"))
    await test_db.commit()
    await client.post("/forgot-password", json={"email": CREDS["email"]})
    await worker.run_once(TestSessionLocal)
    token = _token_from(sent[0])
    assert (await client.post("/reset-password", json={"token": token, "password": "brandnewpass1"})).status_code == 200
    assert (await client.post("/login", json={"username": CREDS["username"], "password": "brandnewpass1"})).status_code == 200


async def test_email_endpoints_are_rate_limited_per_ip(client, test_db, sent):
    codes = [(await client.post("/forgot-password", json={"email": f"x{i}@y.test"})).status_code for i in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]


async def test_register_survives_a_dead_mail_server(client, test_db, monkeypatch):
    """Signup must succeed and be fast even when sending would hang forever."""

    async def hang(message):
        await asyncio.sleep(30)

    monkeypatch.setattr(worker, "send_email", hang)
    start = time.perf_counter()
    resp = await _register(client)
    assert resp.status_code == 200 and time.perf_counter() - start < 2
