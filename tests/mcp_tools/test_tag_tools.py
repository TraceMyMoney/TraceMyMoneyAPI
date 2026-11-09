"""Tests for the MCP tag tools (tags-crud Step 3).

The tools run for real against the real FastAPI app (in-process, no network):
the MCP client's HTTP layer is pointed at the app through ASGITransport, so
these cover tool -> API -> service -> test database.
"""

import pytest
from httpx import ASGITransport, AsyncClient

pytest.importorskip("fastmcp")  # the MCP server is an optional extra

from fastmcp.server.auth import AccessToken  # noqa: E402

from main import app  # noqa: E402
from mcp_server import server  # noqa: E402
from mcp_server.client import StalkMyMoneyClient, StalkMyMoneyError  # noqa: E402


class SpyClient(StalkMyMoneyClient):
    """Real client over ASGI that remembers every call it made."""

    def __init__(self):
        super().__init__(base_url="http://test")
        self._http = AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")
        self.calls = []

    async def request_json(self, method, path, *, token, **kwargs):
        self.calls.append((method, path))
        return await super().request_json(method, path, token=token, **kwargs)


@pytest.fixture
def mcp_auth(client, auth_headers, monkeypatch):
    """`client` is requested so the app is wired to the test DB. Returns the
    AccessToken a tool receives, and swaps the server's client for the spy."""
    spy = SpyClient()
    monkeypatch.setattr(server, "client", spy)
    token = auth_headers["Authorization"].split()[1]
    auth = AccessToken(client_id="stalkmymoney", scopes=["mcp"], token=token)
    return auth


async def _entries_with_tag(client, auth_headers, bank_id, tag_id, n):
    resp = await client.post(
        "/expenses/create",
        json={
            "bank_id": bank_id,
            "expenses": [
                {"amount": 10.0 + i, "description": f"e{i}", "entry_tags": [tag_id], "type": "expense"}
                for i in range(n)
            ],
            "created_at": "01/01/2026 00:00",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


async def test_create_and_list_tags_show_capitalized_name_and_count(mcp_auth, client, auth_headers, created_bank):
    created = await server.create_tag("fuel", auth=mcp_auth)
    assert created["name"] == "Fuel"
    await _entries_with_tag(client, auth_headers, created_bank["id"], created["tag_id"], 2)
    listed = await server.list_tags(auth=mcp_auth)
    assert [(t["name"], t["entry_count"]) for t in listed] == [("Fuel", 2)]


async def test_rename_tag_by_name_any_case(mcp_auth):
    await server.create_tag("food", auth=mcp_auth)
    result = await server.rename_tag("  FOOD ", "groceries", auth=mcp_auth)
    assert result["renamed_from"] == "Food" and result["renamed_to"] == "Groceries"
    assert [t["name"] for t in await server.list_tags(auth=mcp_auth)] == ["Groceries"]


async def test_rename_tag_by_id_works_too(mcp_auth):
    created = await server.create_tag("food", auth=mcp_auth)
    result = await server.rename_tag(created["tag_id"], "Meals", auth=mcp_auth)
    assert result["renamed_to"] == "Meals"


async def test_rename_tag_validates_input_before_calling_the_api(mcp_auth):
    await server.create_tag("food", auth=mcp_auth)
    server.client.calls.clear()
    with pytest.raises(ValueError, match="empty"):
        await server.rename_tag("food", "   ", auth=mcp_auth)
    with pytest.raises(ValueError, match="50 characters"):
        await server.rename_tag("food", "x" * 51, auth=mcp_auth)
    assert not [c for c in server.client.calls if c[0] == "PATCH"]


async def test_rename_tag_unknown_name_lists_your_tags(mcp_auth):
    await server.create_tag("food", auth=mcp_auth)
    with pytest.raises(ValueError, match="Your tags: Food"):
        await server.rename_tag("nope", "Anything", auth=mcp_auth)


async def test_rename_to_a_taken_name_gives_the_api_message(mcp_auth):
    await server.create_tag("food", auth=mcp_auth)
    await server.create_tag("rent", auth=mcp_auth)
    with pytest.raises(StalkMyMoneyError, match="already exists"):
        await server.rename_tag("rent", "FOOD", auth=mcp_auth)


async def test_delete_without_confirm_deletes_nothing_and_reports_count(mcp_auth, client, auth_headers, created_bank):
    created = await server.create_tag("fuel", auth=mcp_auth)
    await _entries_with_tag(client, auth_headers, created_bank["id"], created["tag_id"], 3)
    server.client.calls.clear()

    result = await server.delete_tag("fuel", auth=mcp_auth)

    assert result["deleted"] is False and result["needs_confirmation"] is True
    assert result["entries_affected"] == 3 and result["tag"] == "Fuel"
    assert not [c for c in server.client.calls if c[0] == "DELETE"]  # no DELETE was even sent
    assert [t["name"] for t in await server.list_tags(auth=mcp_auth)] == ["Fuel"]


async def test_delete_with_confirm_deletes_and_keeps_entries(mcp_auth, client, auth_headers, created_bank):
    created = await server.create_tag("fuel", auth=mcp_auth)
    await _entries_with_tag(client, auth_headers, created_bank["id"], created["tag_id"], 3)

    result = await server.delete_tag("fuel", confirm=True, auth=mcp_auth)

    assert result == {"deleted": "Fuel", "entries_untagged": 3}
    assert await server.list_tags(auth=mcp_auth) == []
    assert "e0" in str((await client.get("/expenses/", headers=auth_headers)).json())  # entries survive


async def test_delete_unknown_tag_is_a_clear_error_and_deletes_nothing(mcp_auth):
    await server.create_tag("food", auth=mcp_auth)
    server.client.calls.clear()
    with pytest.raises(ValueError, match="No tag matches"):
        await server.delete_tag("nope", confirm=True, auth=mcp_auth)
    assert not [c for c in server.client.calls if c[0] == "DELETE"]


def test_delete_tag_docstring_marks_it_destructive_and_explains_confirm():
    doc = server.delete_tag.__doc__
    assert "DESTRUCTIVE" in doc and "confirm=true" in doc and "entries_affected" in doc
