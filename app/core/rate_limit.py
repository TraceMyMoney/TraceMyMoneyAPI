"""Tiny in-memory per-IP rate limiter for the endpoints that can trigger an email
(otherwise they are a spam cannon). Best effort: per process, resets on restart.
The per-account cooldown in AccountEmailService is the durable limit; this one
just stops one address hammering the endpoints."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_hits: dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    # nginx appends the real client address to X-Forwarded-For; the last entry is
    # the one our own proxy added, so it cannot be forged by the caller.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(bucket: str, limit: int, window_seconds: int):
    """FastAPI dependency: at most `limit` calls per `window_seconds` per IP."""

    async def dependency(request: Request) -> None:
        key = f"{bucket}:{client_ip(request)}"
        now = time.monotonic()
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, please try again later.")
        hits.append(now)

    return dependency


def reset_rate_limits() -> None:
    """For tests."""
    _hits.clear()
