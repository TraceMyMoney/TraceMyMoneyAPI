"""Mailgun sender + templates. The HTTP call is mocked: no real email is ever sent."""

import httpx
import pytest

from app.core.config import settings
from app.services.email import sender, templates
from app.services.email.sender import Attachment, EmailMessage, EmailSendError, send_email


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "MAILGUN_API_KEY", "key-test")
    monkeypatch.setattr(settings, "MAILGUN_URI", "https://api.mailgun.net/v3/example.test/messages")
    monkeypatch.setattr(settings, "MAILGUN_FROM_ADDR", "me@example.test")


def _mock_mailgun(monkeypatch, handler):
    """Make the sender's httpx.AsyncClient talk to `handler` instead of the network."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(sender.httpx, "AsyncClient", factory)


MSG = EmailMessage(to="a@b.test", subject="Hi", html="<b>hi</b>", text="hi")


async def test_unconfigured_uses_console_and_never_calls_network(monkeypatch):
    monkeypatch.setattr(settings, "MAILGUN_API_KEY", "")

    def boom(request):
        raise AssertionError("network must not be touched")

    _mock_mailgun(monkeypatch, boom)
    await send_email(MSG)  # no exception, nothing sent


async def test_posts_to_mailgun_with_basic_auth_and_form_fields(monkeypatch):
    _configure(monkeypatch)
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"id": "<1>", "message": "Queued"})

    _mock_mailgun(monkeypatch, handler)
    await send_email(MSG)

    assert seen["url"] == "https://api.mailgun.net/v3/example.test/messages"
    assert seen["auth"].startswith("Basic ")  # ("api", key)
    assert "me%40example.test" in seen["body"] or "me@example.test" in seen["body"]
    assert "a%40b.test" in seen["body"] or "a@b.test" in seen["body"]


async def test_attachment_is_sent_as_multipart(monkeypatch):
    _configure(monkeypatch)
    seen = {}

    def handler(request: httpx.Request):
        seen["ctype"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json={})

    _mock_mailgun(monkeypatch, handler)
    msg = EmailMessage(
        to="a@b.test", subject="r", html="x", text="x",
        attachments=[Attachment("report.pdf", b"%PDF-fake", "application/pdf")],
    )
    await send_email(msg)

    assert seen["ctype"].startswith("multipart/form-data")
    assert b'name="attachment"; filename="report.pdf"' in seen["body"]
    assert b"%PDF-fake" in seen["body"]


@pytest.mark.parametrize("status", [500, 502, 429])
async def test_server_errors_are_retryable(monkeypatch, status):
    _configure(monkeypatch)
    _mock_mailgun(monkeypatch, lambda r: httpx.Response(status, text="try later"))
    with pytest.raises(EmailSendError) as e:
        await send_email(MSG)
    assert e.value.permanent is False


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_client_errors_are_permanent(monkeypatch, status):
    _configure(monkeypatch)
    _mock_mailgun(monkeypatch, lambda r: httpx.Response(status, text="nope"))
    with pytest.raises(EmailSendError) as e:
        await send_email(MSG)
    assert e.value.permanent is True


async def test_network_failure_is_retryable(monkeypatch):
    _configure(monkeypatch)

    def handler(request):
        raise httpx.ConnectTimeout("slow")

    _mock_mailgun(monkeypatch, handler)
    with pytest.raises(EmailSendError) as e:
        await send_email(MSG)
    assert e.value.permanent is False


def test_templates_escape_user_supplied_values():
    evil = '<script>alert(1)</script>@x.test'
    subject, html, text = templates.verify_email(evil, 'https://app.test/verify-email?token=a"b')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert 'token=a"b' not in html  # quote escaped inside the href
    assert "https://app.test/verify-email" in text


def test_report_template_mentions_attachment_name():
    subject, html, text = templates.expense_report("Expenses - Food", "12 entries, total 3,400", "expenses.pdf")
    assert "expenses.pdf" in html and "expenses.pdf" in text
    assert "Food" in subject
