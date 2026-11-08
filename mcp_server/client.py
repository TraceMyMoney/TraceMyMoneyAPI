"""Thin stateless async HTTP client for the StalkMyMoney API.

No stored token and no session: every call receives the caller's OAuth access
token and forwards it as a Bearer header, so one MCP process safely serves many
users. The API's `get_current_user` accepts that token like a normal login.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


class StalkMyMoneyError(RuntimeError):
    """A non-2xx API response; carries the API's own `detail` message."""


class StalkMyMoneyClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("SMM_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail: Any = None
        try:
            detail = response.json().get("detail")
        except Exception:
            pass
        if isinstance(detail, list):  # FastAPI validation errors
            detail = "; ".join(str(d.get("msg", d)) for d in detail)
        raise StalkMyMoneyError(str(detail or f"{response.request.method} {response.request.url.path} -> {response.status_code}"))

    async def request_json(self, method: str, path: str, *, token: str, **kwargs: Any) -> Any:
        if not token:
            raise StalkMyMoneyError("Not signed in. Reconnect the StalkMyMoney connector in Claude.")
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = f"Bearer {token}"
        response = await self._http.request(method, path, headers=headers, **kwargs)
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()
