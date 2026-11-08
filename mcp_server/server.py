"""StalkMyMoney MCP server.

Exposes the StalkMyMoney API as MCP tools so Claude (claude.ai connector, or
any MCP client) can read and record expenses by conversation. Stateless: every
user signs in through the OAuth flow in Claude's connector UI, and the OAuth
access token is forwarded to the API on every tool call.

Auth flow (same shape as the MarkdownStack connector):
  1. Claude -> GET /.well-known/oauth-protected-resource (via /mcp/.well-known/)
  2. Claude -> GET /.well-known/oauth-authorization-server, POST /oauth/register
  3. Browser -> /oauth/authorize -> the app's approval page -> user clicks Authorize
  4. Claude -> POST /oauth/token (code + PKCE) -> 90 day access token
  5. Claude sends it as the Bearer on every MCP request; verify_token below
     asks the API (GET /oauth/validate) whether it is live.

Run:
    python -m mcp_server.server                       stdio (local clients)
    SMM_MCP_TRANSPORT=http python -m mcp_server.server  Streamable HTTP (EC2)

Environment:
    SMM_API_BASE_URL    API base URL (default http://localhost:8000)
    SMM_MCP_TRANSPORT   "stdio" (default) or "http"
    SMM_MCP_HOST/PORT/PATH   http mode bind (0.0.0.0 / 8090 / /mcp)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Literal, Optional

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import CurrentAccessToken

try:
    from .client import StalkMyMoneyClient, StalkMyMoneyError
except ImportError:  # run as a script: fastmcp run mcp_server/server.py
    from client import StalkMyMoneyClient, StalkMyMoneyError


class StalkMyMoneyTokenVerifier(TokenVerifier):
    """Accept a connection only if the API says its Bearer token is live."""

    async def verify_token(self, token: str) -> AccessToken | None:
        api_base = (os.getenv("SMM_API_BASE_URL") or "http://localhost:8000").rstrip("/")
        try:
            async with httpx.AsyncClient(base_url=api_base, timeout=10.0) as http:
                resp = await http.get("/oauth/validate", headers={"Authorization": f"Bearer {token}"})
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        return AccessToken(client_id="stalkmymoney", scopes=["mcp"], token=token)


mcp = FastMCP("stalkmymoney", auth=StalkMyMoneyTokenVerifier())
client = StalkMyMoneyClient()


# ---- helpers --------------------------------------------------------------


def _api_date(day: str, end_of_day: bool = False) -> str:
    """'YYYY-MM-DD' -> the API's 'D/M/YYYY HH:MM'. The API silently turns an
    unparseable date into *now*, so validate here instead of passing it on."""
    try:
        d = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Dates must be YYYY-MM-DD, got {day!r}")
    return f"{d.day}/{d.month}/{d.year} {'23:59' if end_of_day else '00:00'}"


async def _banks(token: str) -> list[dict]:
    return (await client.request_json("GET", "/banks/", token=token))["banks"]


async def _tags(token: str) -> list[dict]:
    return (await client.request_json("GET", "/entry-tags/", token=token))["entry_tags"]


async def _resolve_bank(token: str, bank: str) -> dict:
    """Accept an account id or its name (case-insensitive)."""
    banks = await _banks(token)
    for b in banks:
        if b["id"] == bank:
            return b
    named = [b for b in banks if b["name"].strip().lower() == bank.strip().lower()]
    if len(named) == 1:
        return named[0]
    options = ", ".join(b["name"] for b in banks) or "none yet"
    raise ValueError(f"No account matches {bank!r}. Your accounts: {options}")


async def _resolve_tag_ids(token: str, names: list[str] | None, create_missing: bool) -> list[str]:
    """Tag names (or ids) -> tag ids. Unknown names are created when allowed."""
    if not names:
        return []
    existing = await _tags(token)
    by_name = {t["name"].strip().lower(): t["id"] for t in existing}
    ids = {t["id"] for t in existing}
    out: list[str] = []
    for n in names:
        if n in ids:
            out.append(n)
        elif n.strip().lower() in by_name:
            out.append(by_name[n.strip().lower()])
        elif create_missing:
            created = await client.request_json("POST", "/entry-tags/create", token=token, json={"name": n.strip()})
            by_name[n.strip().lower()] = created["tag_id"]
            out.append(created["tag_id"])
        else:
            raise ValueError(f"Unknown tag {n!r}. Existing tags: {', '.join(t['name'] for t in existing) or 'none'}")
    return out


# ---- account ---------------------------------------------------------------


@mcp.tool()
async def whoami(auth: AccessToken = CurrentAccessToken()) -> dict:
    """The signed-in StalkMyMoney user (username and email)."""
    return await client.request_json("GET", "/profile/", token=auth.token)


@mcp.tool()
async def list_accounts(auth: AccessToken = CurrentAccessToken()) -> list:
    """Your accounts (banks, cards, wallets) with current balance and the
    total spent so far. Account names are what you refer to elsewhere."""
    return await _banks(auth.token)


@mcp.tool()
async def create_account(
    name: str,
    opening_balance: float,
    auth: AccessToken = CurrentAccessToken(),
) -> dict:
    """Create an account. `name` is at most 20 characters; `opening_balance`
    must be greater than 0 and becomes both the initial and current balance."""
    await client.request_json(
        "POST",
        "/banks/create",
        token=auth.token,
        json={"name": name, "initial_balance": opening_balance, "current_balance": opening_balance},
    )
    return await _resolve_bank(auth.token, name)


@mcp.tool()
async def delete_account(account: str, auth: AccessToken = CurrentAccessToken()) -> dict:
    """Permanently delete an account AND every expense recorded in it. Cannot
    be undone - confirm with the user first. `account` is a name or id."""
    bank = await _resolve_bank(auth.token, account)
    await client.request_json("DELETE", "/banks/delete", token=auth.token, params={"bank_id": bank["id"]})
    return {"deleted": bank["name"]}


# ---- tags -------------------------------------------------------------------


@mcp.tool()
async def list_tags(auth: AccessToken = CurrentAccessToken()) -> list:
    """Your expense tags (categories such as food, rent, travel)."""
    return await _tags(auth.token)


@mcp.tool()
async def create_tag(name: str, auth: AccessToken = CurrentAccessToken()) -> dict:
    """Create a tag (max 50 characters). Tags are matched by name elsewhere,
    so this is only needed to create one ahead of time."""
    return await client.request_json("POST", "/entry-tags/create", token=auth.token, json={"name": name})


# ---- reading expenses -------------------------------------------------------


@mcp.tool()
async def list_expenses(
    auth: AccessToken = CurrentAccessToken(),
    account: Optional[str] = None,
    tags: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
    keyword: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    match_all_tags: bool = True,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """List expenses, newest first. One expense is one day in one account and
    holds several entries (amount, description, tags). Negative amounts are
    credits / top-ups. Every filter is optional:
      account       name or id (omit for all accounts)
      tags          only entries with these tag names (all of them, or any if
                    match_all_tags=False)
      exclude_tags  hide entries with these tag names
      keyword       substring of the entry description
      start_date / end_date   YYYY-MM-DD, inclusive
    Returns the page of expenses plus total count, and the debit and credit
    totals across ALL matches (not just this page)."""
    token = auth.token
    params: dict = {"page_number": page, "per_page": per_page, "advanced_search": True}
    if account:
        params["bank_id"] = (await _resolve_bank(token, account))["id"]
    if tags:
        params["search_by_tags"] = await _resolve_tag_ids(token, tags, create_missing=False)
    if exclude_tags:
        params["exclude_tags"] = await _resolve_tag_ids(token, exclude_tags, create_missing=False)
    if keyword:
        params["search_by_keyword"] = keyword
    if start_date or end_date:
        params["search_by_daterange"] = {
            "start_date": _api_date(start_date or "1970-01-01"),
            **({"end_date": _api_date(end_date, end_of_day=True)} if end_date else {}),
        }
    params["operator"] = "and" if match_all_tags else "or"
    return await client.request_json("GET", "/expenses/", token=token, params={"data": json.dumps(params)})


@mcp.tool()
async def spending_overview(
    auth: AccessToken = CurrentAccessToken(),
    accounts: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
    keyword: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """Spending totals grouped by account, by tag and by day - the numbers
    behind the Analytics charts. Use it for "how much did I spend on food in
    October?". Filters as in list_expenses (dates are YYYY-MM-DD)."""
    token = auth.token
    params: dict = {}
    if accounts:
        params["bank_id"] = [(await _resolve_bank(token, a))["id"] for a in accounts]
    if tags:
        params["tag_id"] = await _resolve_tag_ids(token, tags, create_missing=False)
    if exclude_tags:
        params["exclude_tag_id"] = await _resolve_tag_ids(token, exclude_tags, create_missing=False)
    if keyword:
        params["keyword"] = keyword
    if start_date:
        _api_date(start_date)
        params["start_date"] = start_date
    if end_date:
        _api_date(end_date)
        params["end_date"] = end_date
    return await client.request_json("GET", "/expenses/analytics/overview", token=token, params=params)


# ---- writing expenses -------------------------------------------------------


@mcp.tool()
async def add_expense(
    account: str,
    amount: float,
    description: str = "",
    tags: Optional[list[str]] = None,
    kind: Literal["debit", "credit"] = "debit",
    date: Optional[str] = None,
    auth: AccessToken = CurrentAccessToken(),
) -> dict:
    """Record one transaction. `amount` is always positive; kind="debit" is
    money spent, kind="credit" is money received (stored as a negative entry,
    which raises the balance). `account` is a name or id. `tags` are names;
    unknown names are created. `date` is YYYY-MM-DD (default today).

    If that account already has an expense for that day the entry is appended
    to it, otherwise a new day is created - the same rule the app uses."""
    if amount <= 0:
        raise ValueError("amount must be greater than 0; use kind='credit' for money received")
    token = auth.token
    bank = await _resolve_bank(token, account)
    tag_ids = await _resolve_tag_ids(token, tags, create_missing=True)
    entry = {
        "amount": amount if kind == "debit" else -amount,
        "description": description[:200],
        "entry_tags": tag_ids,
        "type": "expense",
    }
    day = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    day_str = f"{day.day}/{day.month}/{day.year} 00:00"

    # An account can hold only one expense per day: append if it exists.
    day_filter = {
        "bank_id": bank["id"],
        "advanced_search": True,
        "per_page": 1,
        "search_by_daterange": {"start_date": day_str, "end_date": f"{day.day}/{day.month}/{day.year} 23:59"},
    }
    found = await client.request_json("GET", "/expenses/", token=token, params={"data": json.dumps(day_filter)})
    if found["expenses"]:
        expense_id = found["expenses"][0]["id"]
        await client.request_json(
            "PATCH", "/expenses/add-entry", token=token, params={"id": expense_id}, json={"entries": [entry]}
        )
        return {"result": "added to the existing day", "expense_id": expense_id, "account": bank["name"]}
    created = await client.request_json(
        "POST", "/expenses/create", token=token, json={"bank_id": bank["id"], "expenses": [entry], "created_at": day_str}
    )
    return {"result": "created a new day", "expense_id": created["_id"], "account": bank["name"]}


@mcp.tool()
async def update_entry(
    expense_id: str,
    entry_id: str,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    auth: AccessToken = CurrentAccessToken(),
) -> dict:
    """Change an entry's description and/or tags (not its amount - delete and
    re-add for that). Ids come from list_expenses (`id` and each entry's
    `ee_id`). `tags` replaces the entry's tags; unknown names are created."""
    if description is None and not tags:
        raise ValueError("Pass a new description and/or tags")
    tag_ids = await _resolve_tag_ids(auth.token, tags, create_missing=True) if tags else None
    payload = {"expense_id": expense_id, "entry_id": entry_id, "updated_description": description, "entry_tags": tag_ids}
    return await client.request_json("PATCH", "/expenses/update-entry", token=auth.token, json=payload)


@mcp.tool()
async def delete_entry(expense_id: str, entry_id: str, auth: AccessToken = CurrentAccessToken()) -> dict:
    """Delete one entry from a day's expense. Confirm with the user first."""
    await client.request_json(
        "DELETE", "/expenses/delete-entry", token=auth.token, params={"id": expense_id, "ee_id": entry_id}
    )
    return {"deleted_entry": entry_id}


@mcp.tool()
async def delete_expense(expense_id: str, auth: AccessToken = CurrentAccessToken()) -> dict:
    """Delete a whole day's expense and all its entries. Confirm first."""
    await client.request_json("DELETE", "/expenses/delete", token=auth.token, params={"id": expense_id})
    return {"deleted_expense": expense_id}


# ---- SMS review list --------------------------------------------------------


@mcp.tool()
async def list_pending_sms(auth: AccessToken = CurrentAccessToken()) -> list:
    """Bank SMS transactions captured automatically that are waiting for your
    review (the SMS didn't name one of your accounts, or auto-add is off)."""
    return (await client.request_json("GET", "/ingest/pending", token=auth.token))["transactions"]


@mcp.tool()
async def confirm_pending_sms(
    pending_id: str,
    account: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    amount: Optional[float] = None,
    auth: AccessToken = CurrentAccessToken(),
) -> dict:
    """Add a waiting SMS transaction to your expenses. Pass `account` (name or
    id) unless the item already has one; `amount` only to correct a misread."""
    token = auth.token
    payload: dict = {"entry_tags": await _resolve_tag_ids(token, tags, create_missing=True)}
    if account:
        payload["bank_id"] = (await _resolve_bank(token, account))["id"]
    if description is not None:
        payload["description"] = description
    if amount is not None:
        payload["amount"] = amount
    return await client.request_json("POST", f"/ingest/pending/{pending_id}/confirm", token=token, json=payload)


@mcp.tool()
async def dismiss_pending_sms(pending_id: str, auth: AccessToken = CurrentAccessToken()) -> dict:
    """Discard a waiting SMS transaction (it is not added to expenses)."""
    return await client.request_json("DELETE", f"/ingest/pending/{pending_id}", token=auth.token)


# ---- run --------------------------------------------------------------------


def run() -> None:
    transport = os.getenv("SMM_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
        return
    mcp.run(
        transport=transport,
        host=os.getenv("SMM_MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("SMM_MCP_PORT", "8090")),
        path=os.getenv("SMM_MCP_PATH", "/mcp"),
    )


if __name__ == "__main__":
    run()
