"""In-memory token-usage metrics for the chat agent, surfaced on the
admin dashboard's Usage tab. Same philosophy as llm_status.py: process-
local, best-effort, reset on restart - this is an operational "how much
are we actually sending the LLM per request" view, not a billing system
of record (use the provider's own dashboard/invoices for that)."""

from collections import deque
from datetime import datetime, timezone

# Capped so this can never grow unbounded - old entries just age out.
# Still large enough to cover a very busy day's worth of chat turns for
# visibility purposes.
_MAX_RECENT = 300

_recent: deque[dict] = deque(maxlen=_MAX_RECENT)

# Cumulative since this process started - never evicted, unlike _recent,
# so "lifetime" totals stay accurate even once older requests have aged
# out of the recent list above.
_lifetime = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def record_request(
    provider: str,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    category: str | None = None,
) -> None:
    """Call once per completed chat turn that actually hit the LLM (skip
    this for fast-path/cached responses that never called it at all -
    see AgentChatService, which only calls this after a real graph run)."""
    total = input_tokens + output_tokens
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "category": category,
    }
    _recent.append(entry)
    _lifetime["requests"] += 1
    _lifetime["input_tokens"] += input_tokens
    _lifetime["output_tokens"] += output_tokens
    _lifetime["total_tokens"] += total


def get_metrics(limit: int = 50) -> dict:
    """`recent`: the most recent `limit` requests, newest first.
    `today`: best-effort totals for entries still in the (capped) recent
    buffer whose timestamp falls on today's UTC date - undercounts if
    more than _MAX_RECENT requests happened today, which is fine for an
    at-a-glance admin view, not acceptable for anything billing-related.
    `lifetime`: exact cumulative totals since this process started."""
    today_str = datetime.now(timezone.utc).date().isoformat()
    today_entries = [e for e in _recent if e["at"].startswith(today_str)]
    today_totals = {
        "requests": len(today_entries),
        "input_tokens": sum(e["input_tokens"] for e in today_entries),
        "output_tokens": sum(e["output_tokens"] for e in today_entries),
        "total_tokens": sum(e["total_tokens"] for e in today_entries),
    }
    recent_list = list(_recent)[-limit:][::-1]
    return {"recent": recent_list, "today": today_totals, "lifetime": dict(_lifetime)}
