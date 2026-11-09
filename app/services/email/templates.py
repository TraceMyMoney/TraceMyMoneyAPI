"""Email bodies. Inline styles only (email clients ignore stylesheets), dark
card with the app's acid-green button. Every user-supplied value is escaped."""

from html import escape

from app.core.config import settings

_BG = "#0b0b0c"
_CARD = "#151517"
_TEXT = "#e8e8ea"
_MUTED = "#8a8a92"
_ACID = "#B8FF00"


def _shell(title: str, body_html: str, cta_url: str | None = None, cta_label: str | None = None, footer: str = "") -> str:
    button = ""
    link_fallback = ""
    if cta_url and cta_label:
        url = escape(cta_url, quote=True)
        button = f"""
      <p style="margin:28px 0;">
        <a href="{url}" style="display:inline-block;background:{_ACID};color:{_BG};padding:13px 24px;
           border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;letter-spacing:.3px;">{escape(cta_label)}</a>
      </p>"""
        link_fallback = f"""
      <p style="font-size:12px;line-height:1.5;color:{_MUTED};margin:0;">
        Or paste this link into your browser:<br>
        <a href="{url}" style="color:{_MUTED};word-break:break-all;">{url}</a>
      </p>"""
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:{_BG};">
  <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
              max-width:480px;margin:0 auto;padding:32px 16px;">
    <div style="background:{_CARD};border-radius:14px;padding:32px 28px;color:{_TEXT};">
      <p style="margin:0 0 20px;font-size:12px;letter-spacing:2px;text-transform:uppercase;color:{_ACID};font-weight:700;">
        {escape(settings.EMAIL_FROM_NAME)}</p>
      <h1 style="font-size:21px;margin:0 0 14px;color:#fff;">{escape(title)}</h1>
      <div style="font-size:14px;line-height:1.65;color:{_TEXT};">{body_html}</div>
      {button}
      {link_fallback}
      {f'<p style="font-size:12px;line-height:1.5;color:{_MUTED};margin:22px 0 0;">{footer}</p>' if footer else ''}
    </div>
  </div>
</body></html>"""


def verify_email(to_email: str, link: str) -> tuple[str, str, str]:
    """(subject, html, text) for the signup confirmation."""
    subject = f"Confirm your {settings.EMAIL_FROM_NAME} email"
    html = _shell(
        "Confirm your email",
        f"Welcome! Confirm <strong>{escape(to_email)}</strong> to activate your account. "
        "This link expires in 24 hours.",
        cta_url=link,
        cta_label="Verify email address",
        footer="Didn't sign up? You can safely ignore this email.",
    )
    text = f"Confirm your {settings.EMAIL_FROM_NAME} account (link valid for 24 hours): {link}\n\nDidn't sign up? Ignore this email."
    return subject, html, text


def reset_password(to_email: str, link: str) -> tuple[str, str, str]:
    """(subject, html, text) for the password-reset link."""
    subject = f"Reset your {settings.EMAIL_FROM_NAME} password"
    html = _shell(
        "Reset your password",
        f"We got a request to reset the password for <strong>{escape(to_email)}</strong>. "
        "This link expires in 1 hour and works once.",
        cta_url=link,
        cta_label="Reset password",
        footer="Didn't ask for this? Ignore this email - your password won't change.",
    )
    text = f"Reset your {settings.EMAIL_FROM_NAME} password (link valid for 1 hour): {link}\n\nDidn't ask for this? Ignore this email."
    return subject, html, text


def expense_report(title: str, summary: str, filename: str) -> tuple[str, str, str]:
    """(subject, html, text) for the chatbot's emailed expense PDF."""
    subject = f"{settings.EMAIL_FROM_NAME}: {title}"
    html = _shell(
        title,
        f"{escape(summary)}<br><br>Your report is attached as <strong>{escape(filename)}</strong>.",
        footer="You asked the chatbot to email this report.",
    )
    text = f"{title}\n\n{summary}\n\nYour report is attached as {filename}.\nYou asked the chatbot to email this report."
    return subject, html, text
