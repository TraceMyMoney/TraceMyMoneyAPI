"""Chatbot: export_expenses (download) never emails; email_expenses (email) only on an
explicit ask, only to the account's own address, and in the background."""

import pytest
from sqlalchemy import func, select

from app.db.tables import email_jobs
from app.services.agent.tools import MAX_REPORT_EMAILS_PER_HOUR, build_tools, mask_email
from app.services.email import worker
from tests.conftest import TestSessionLocal


@pytest.fixture
def sent(monkeypatch):
    box = []

    async def fake_send(message):
        box.append(message)

    monkeypatch.setattr(worker, "send_email", fake_send)
    return box


@pytest.fixture
async def seeded(client, auth_headers, created_bank, registered_user):
    """One expense (50 debit, 20 credit) on a known day in the user's bank."""
    payload = {
        "bank_id": created_bank["id"],
        "expenses": [
            {"description": "lunch", "amount": 50.0, "tags": []},
            {"description": "refund", "amount": -20.0, "tags": []},
        ],
    }
    resp = await client.post("/expenses/create", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return registered_user["user_id"], created_bank["name"]


def _tools(user_id, db, box=None):
    return {t.name: t for t in build_tools(user_id, db, export_box=box)}


async def _jobs(db):
    """Report-email jobs only (signup in the fixtures queues its own verify email)."""
    return (
        await db.execute(select(func.count()).select_from(email_jobs).where(email_jobs.c.kind == "expense_report"))
    ).scalar_one()


async def test_download_never_creates_an_email_job(test_db, seeded):
    user_id, _ = seeded
    box = {}
    out = await _tools(user_id, test_db, box)["export_expenses"].ainvoke({"format": "pdf"})
    assert out.startswith("Exported") and box["filename"].endswith(".pdf") and box["content_b64"]
    assert await _jobs(test_db) == 0


async def test_email_without_explicit_ask_sends_nothing(test_db, seeded):
    user_id, _ = seeded
    out = await _tools(user_id, test_db)["email_expenses"].ainvoke({"user_asked_for_email": False})
    assert "Nothing was sent" in out
    assert await _jobs(test_db) == 0


async def test_explicit_email_queues_one_job_and_the_worker_sends_a_pdf(test_db, seeded, sent):
    user_id, bank = seeded
    out = await _tools(user_id, test_db)["email_expenses"].ainvoke({"user_asked_for_email": True, "bank_name": bank})
    assert out.startswith("Queued") and "c***@example.com" in out
    assert await _jobs(test_db) == 1
    assert sent == []  # replying to the chat did not wait for any sending (nothing was sent yet)

    await worker.run_once(TestSessionLocal)
    report_mails = [m for m in sent if m.attachments]  # the signup verify email is also in the queue
    assert len(report_mails) == 1
    msg = report_mails[0]
    assert msg.to == "characterization@example.com"  # the account's own address, nobody else's
    assert len(msg.attachments) == 1
    att = msg.attachments[0]
    assert att.filename.endswith(".pdf") and att.mime_type == "application/pdf" and att.content.startswith(b"%PDF")


async def test_empty_result_and_unknown_bank_answer_in_chat_without_a_job(test_db, seeded):
    user_id, _ = seeded
    tools = _tools(user_id, test_db)
    out = await tools["email_expenses"].ainvoke(
        {"user_asked_for_email": True, "start_date": "01/01/2000", "end_date": "02/01/2000"}
    )
    assert "No matching expenses" in out
    out = await tools["email_expenses"].ainvoke({"user_asked_for_email": True, "bank_name": "NoSuchBank"})
    assert "No bank account named" in out
    assert await _jobs(test_db) == 0


async def test_report_emails_are_capped_per_hour(test_db, seeded):
    user_id, _ = seeded
    tool = _tools(user_id, test_db)["email_expenses"]
    for _ in range(MAX_REPORT_EMAILS_PER_HOUR):
        assert (await tool.ainvoke({"user_asked_for_email": True})).startswith("Queued")
    assert "Not sent" in await tool.ainvoke({"user_asked_for_email": True})
    assert await _jobs(test_db) == MAX_REPORT_EMAILS_PER_HOUR


async def test_tool_has_no_recipient_argument(test_db, seeded):
    user_id, _ = seeded
    args = set(_tools(user_id, test_db)["email_expenses"].args)
    assert not ({"to", "email", "recipient", "to_email", "address"} & args)


def test_mask_email():
    assert mask_email("parimal@gmail.com") == "p***@gmail.com"
    assert mask_email("weird") == "your account email"
