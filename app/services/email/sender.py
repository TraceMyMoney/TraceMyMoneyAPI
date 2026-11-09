"""Send one email through the Mailgun HTTP API.

Modelled on obsidian-clone's users/email.py (httpx, basic auth ("api", key),
form fields from/to/subject/html/text), with two differences:

* it RAISES on failure instead of swallowing the error, because the outbox
  worker (worker.py) decides about retries;
* it supports attachments (Mailgun takes them as multipart "attachment"
  files in the same call) for the expense-report PDF.

If MAILGUN_API_KEY / MAILGUN_URI / MAILGUN_FROM_ADDR are not all set, the
"console" backend is used instead: the email is logged (links included, so
you can click them in local dev) and nothing leaves the machine.
"""

import logging
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 20.0


class EmailSendError(Exception):
    """Sending failed. `permanent=True` means retrying cannot help
    (e.g. Mailgun rejected the request itself); False means try again later."""

    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


@dataclass
class Attachment:
    filename: str
    content: bytes
    mime_type: str


@dataclass
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str
    attachments: list[Attachment] = field(default_factory=list)


def mailgun_configured() -> bool:
    return bool(settings.MAILGUN_API_KEY and settings.MAILGUN_URI and settings.MAILGUN_FROM_ADDR)


def _from_header() -> str:
    return f"{settings.EMAIL_FROM_NAME} <{settings.MAILGUN_FROM_ADDR}>"


async def send_email(message: EmailMessage) -> None:
    """Deliver `message`. Raises EmailSendError on failure."""
    if not mailgun_configured():
        logger.warning(
            "Mailgun not configured - console backend, NOT sending. to=%s subject=%r attachments=%d\n%s",
            message.to,
            message.subject,
            len(message.attachments),
            message.text,
        )
        return

    data = {
        "from": _from_header(),
        "to": message.to,
        "subject": message.subject,
        "html": message.html,
        "text": message.text,
    }
    files = [("attachment", (a.filename, a.content, a.mime_type)) for a in message.attachments] or None

    try:
        async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.MAILGUN_URI,
                auth=("api", settings.MAILGUN_API_KEY),
                data=data,
                files=files,
            )
    except httpx.HTTPError as e:
        # Network trouble / timeout: worth retrying.
        raise EmailSendError(f"Mailgun unreachable: {type(e).__name__}: {e}") from e

    if response.status_code >= 500 or response.status_code == 429:
        raise EmailSendError(f"Mailgun {response.status_code}: {response.text[:200]}")
    if response.status_code >= 400:
        # 401 bad key, 400/403 bad request or unauthorized recipient: retrying won't fix it.
        raise EmailSendError(f"Mailgun rejected the email ({response.status_code}): {response.text[:200]}", permanent=True)
