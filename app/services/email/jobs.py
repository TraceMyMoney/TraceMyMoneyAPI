"""Turn a queued job into a ready-to-send EmailMessage (one builder per kind)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.email import templates
from app.services.email.outbox import KIND_EXPENSE_REPORT, KIND_RESET_PASSWORD, KIND_VERIFY_EMAIL
from app.services.email.sender import Attachment, EmailMessage, EmailSendError


class UnknownJobKind(Exception):
    pass


async def _verify_email(db: AsyncSession, job: dict, to_email: str) -> EmailMessage:
    link = f"{settings.FRONTEND_BASE_URL}/verify-email?token={job['payload']['token']}"
    subject, html, text = templates.verify_email(to_email, link)
    return EmailMessage(to=to_email, subject=subject, html=html, text=text)


async def _reset_password(db: AsyncSession, job: dict, to_email: str) -> EmailMessage:
    link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={job['payload']['token']}"
    subject, html, text = templates.reset_password(to_email, link)
    return EmailMessage(to=to_email, subject=subject, html=html, text=text)


async def _expense_report(db: AsyncSession, job: dict, to_email: str) -> EmailMessage:
    """Build the PDF at send time from the saved filters (the job stores the
    filters, not the file, so the table stays small)."""
    from app.services.agent.report import ReportError, build_report_file, describe_range, gather_export_rows

    filters = job["payload"].get("filters", {})
    fmt = job["payload"].get("format", "pdf")
    try:
        data = await gather_export_rows(db, str(job["user_id"]), filters)
    except ReportError as e:
        # The data changed since it was queued (e.g. entries deleted): retrying won't help.
        raise EmailSendError(str(e), permanent=True) from e
    content, filename, mime = build_report_file(data, fmt)
    total = sum(r["amount"] for r in data.rows)
    summary = f"{len(data.rows)} entries, {describe_range(filters)}. Net total ₹{total:,.2f} (credits are negative)."
    subject, html, text = templates.expense_report(data.title, summary, filename)
    return EmailMessage(to=to_email, subject=subject, html=html, text=text, attachments=[Attachment(filename, content, mime)])


async def build_message(db: AsyncSession, job: dict, to_email: str) -> EmailMessage:
    builder = BUILDERS.get(job["kind"])
    if builder is None:
        raise UnknownJobKind(f"No builder for email job kind {job['kind']!r}")
    return await builder(db, job, to_email)


BUILDERS = {
    KIND_VERIFY_EMAIL: _verify_email,
    KIND_RESET_PASSWORD: _reset_password,
    KIND_EXPENSE_REPORT: _expense_report,
}
