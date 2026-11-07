"""Tiny in-memory record of the most recent LLM-call failure, so the admin
dashboard can show *why* chat is slow/erroring (e.g. "Groq rate limit,
199286/200000 tokens used, retry in 19m") without digging through server
logs. Process-local, best-effort, never a source of truth for anything
else - just a UI convenience. Overwritten by every failure; cleared by
record_llm_success() so a since-resolved issue doesn't show as still
ongoing."""

import re
from datetime import datetime, timezone
from typing import Optional

_last_error: Optional[dict] = None

# Matches Groq's own rate-limit message shape, e.g.:
# "...on tokens per day (TPD): Limit 200000, Used 199286, Requested 3409.
#  Please try again in 19m24.24s."
_GROQ_TPD_RE = re.compile(
    r"Limit (\d+), Used (\d+), Requested (\d+).*?try again in ([\d.]+)m([\d.]+)s",
    re.DOTALL,
)


def record_llm_error(provider: str, exc: Exception) -> None:
    global _last_error
    text = str(exc)
    detail: dict = {"provider": provider, "message": text[:500], "at": datetime.now(timezone.utc).isoformat()}

    match = _GROQ_TPD_RE.search(text)
    if match:
        limit, used, requested, retry_min, retry_sec = match.groups()
        detail["quota"] = {
            "limit": int(limit),
            "used": int(used),
            "requested": int(requested),
            "retry_after_seconds": round(float(retry_min) * 60 + float(retry_sec)),
        }

    _last_error = detail


def record_llm_success() -> None:
    global _last_error
    _last_error = None


def get_last_llm_error() -> Optional[dict]:
    return _last_error
