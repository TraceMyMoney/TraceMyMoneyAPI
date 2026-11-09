"""Tests for the chatbot's tag tools (tags-crud Step 4).

`interrupt()` only works inside a running LangGraph, so these tests replace it
with a fake that records what the user would be shown and answers "approve" or
"decline". The tools, service layer and test database are real.
"""

import pytest
from sqlalchemy import func, select

from app.db.tables import expense_entry_tags
from app.services.agent import tools as agent_tools
from app.services.agent.tools import build_tools


class FakeUser:
    """Stands in for the user at the confirmation step."""

    def __init__(self, answer="approve"):
        self.answer = answer
        self.asked = []  # every confirmation payload shown

    def __call__(self, payload):
        self.asked.append(payload)
        return self.answer


@pytest.fixture
def approve(monkeypatch):
    user = FakeUser("approve")
    monkeypatch.setattr(agent_tools, "interrupt", user)
    return user


@pytest.fixture
def decline(monkeypatch):
    user = FakeUser("decline")
    monkeypatch.setattr(agent_tools, "interrupt", user)
    return user


def _tools(user_id, db):
    return {t.name: t for t in build_tools(user_id, db)}


async def _tag_count(db):
    return (await db.execute(select(func.count()).select_from(expense_entry_tags))).scalar_one()


async def _tagged_entries(client, auth_headers, bank_id, tag_id, n):
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


async def _make_tag(client, auth_headers, name):
    resp = await client.post("/entry-tags/create", json={"name": name}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["tag_id"]


# ---- list_tags ----


async def test_list_tags_shows_counts(client, auth_headers, registered_user, created_bank, test_db, approve):
    used = await _make_tag(client, auth_headers, "fuel")
    await _make_tag(client, auth_headers, "gifts")
    await _tagged_entries(client, auth_headers, created_bank["id"], used, 2)
    out = await _tools(registered_user["user_id"], test_db)["list_tags"].ainvoke({})
    assert "- Fuel (2 entries)" in out and "- Gifts (unused)" in out


# ---- delete_tag ----


async def test_delete_asks_first_with_the_entry_count_and_nothing_happens_before_approval(
    client, auth_headers, registered_user, created_bank, test_db, decline
):
    tag_id = await _make_tag(client, auth_headers, "fuel")
    await _tagged_entries(client, auth_headers, created_bank["id"], tag_id, 3)

    out = await _tools(registered_user["user_id"], test_db)["delete_tag"].ainvoke({"name": "FUEL"})

    assert out.startswith("Cancelled")
    summary = decline.asked[0]["summary"]
    assert "Fuel" in summary and "3 entries" in summary and "lose this tag" in summary
    assert await _tag_count(test_db) == 1  # declined: still there
    assert len((await client.get("/entry-tags/", headers=auth_headers)).json()["entry_tags"]) == 1


async def test_delete_after_approval_removes_the_tag_and_keeps_entries(
    client, auth_headers, registered_user, created_bank, test_db, approve
):
    tag_id = await _make_tag(client, auth_headers, "fuel")
    await _tagged_entries(client, auth_headers, created_bank["id"], tag_id, 3)

    out = await _tools(registered_user["user_id"], test_db)["delete_tag"].ainvoke({"name": "fuel"})

    assert out == "Tag 'Fuel' deleted; 3 entries no longer have it."
    assert await _tag_count(test_db) == 0
    assert "e0" in str((await client.get("/expenses/", headers=auth_headers)).json())


async def test_delete_unused_tag_says_so_and_works_with_zero_entries(
    client, auth_headers, registered_user, test_db, approve
):
    await _make_tag(client, auth_headers, "gifts")
    out = await _tools(registered_user["user_id"], test_db)["delete_tag"].ainvoke({"name": "gifts"})
    assert "not used by any entry" in approve.asked[0]["summary"]
    assert out == "Tag 'Gifts' deleted; 0 entries no longer have it."  # 0 must not read as "not found"
    assert await _tag_count(test_db) == 0


async def test_delete_unknown_tag_does_not_ask_the_user(registered_user, test_db, approve):
    out = await _tools(registered_user["user_id"], test_db)["delete_tag"].ainvoke({"name": "nope"})
    assert out.startswith("No tag named 'nope'")
    assert approve.asked == []


# ---- rename_tag ----


async def test_rename_asks_first_and_nothing_changes_when_declined(
    client, auth_headers, registered_user, test_db, decline
):
    await _make_tag(client, auth_headers, "food")
    out = await _tools(registered_user["user_id"], test_db)["rename_tag"].ainvoke(
        {"old_name": "food", "new_name": "groceries"}
    )
    assert out.startswith("Cancelled")
    assert "Rename tag 'Food' to 'Groceries'" in decline.asked[0]["summary"]
    names = [t["name"] for t in (await client.get("/entry-tags/", headers=auth_headers)).json()["entry_tags"]]
    assert names == ["Food"]


async def test_rename_after_approval_saves_the_capitalized_name(
    client, auth_headers, registered_user, created_bank, test_db, approve
):
    tag_id = await _make_tag(client, auth_headers, "food")
    await _tagged_entries(client, auth_headers, created_bank["id"], tag_id, 2)
    out = await _tools(registered_user["user_id"], test_db)["rename_tag"].ainvoke(
        {"old_name": " FOOD ", "new_name": "groceries"}
    )
    assert out == "Tag renamed to 'Groceries'."
    assert "used by 2 entries" in approve.asked[0]["summary"]
    tags = (await client.get("/entry-tags/", headers=auth_headers)).json()["entry_tags"]
    assert [(t["name"], t["entry_count"]) for t in tags] == [("Groceries", 2)]


@pytest.mark.parametrize("bad", ["   ", "x" * 51])
async def test_rename_rejects_a_bad_new_name_without_asking(
    client, auth_headers, registered_user, test_db, approve, bad
):
    await _make_tag(client, auth_headers, "food")
    out = await _tools(registered_user["user_id"], test_db)["rename_tag"].ainvoke({"old_name": "food", "new_name": bad})
    assert "1 to 50 characters" in out
    assert approve.asked == []


async def test_rename_to_an_existing_name_is_refused_before_asking(
    client, auth_headers, registered_user, test_db, approve
):
    await _make_tag(client, auth_headers, "food")
    await _make_tag(client, auth_headers, "rent")
    out = await _tools(registered_user["user_id"], test_db)["rename_tag"].ainvoke(
        {"old_name": "rent", "new_name": "FOOD"}
    )
    assert "already called 'Food'" in out
    assert approve.asked == []


async def test_rename_unknown_tag_does_not_ask(registered_user, test_db, approve):
    out = await _tools(registered_user["user_id"], test_db)["rename_tag"].ainvoke(
        {"old_name": "nope", "new_name": "Whatever"}
    )
    assert out.startswith("No tag named 'nope'")
    assert approve.asked == []


# ---- create_tag ----


async def test_create_shows_the_saved_name_and_creates_only_after_approval(
    client, auth_headers, registered_user, test_db, decline, monkeypatch
):
    tools = _tools(registered_user["user_id"], test_db)
    assert (await tools["create_tag"].ainvoke({"name": "food"})).startswith("Cancelled")
    assert decline.asked[0]["summary"] == "Create tag 'Food'"
    assert await _tag_count(test_db) == 0

    monkeypatch.setattr(agent_tools, "interrupt", FakeUser("approve"))
    assert await tools["create_tag"].ainvoke({"name": "food"}) == "Tag 'Food' created."
    assert await _tag_count(test_db) == 1


async def test_create_refuses_empty_and_duplicate_names_without_asking(
    client, auth_headers, registered_user, test_db, approve
):
    await _make_tag(client, auth_headers, "food")
    tools = _tools(registered_user["user_id"], test_db)
    assert "1 to 50 characters" in await tools["create_tag"].ainvoke({"name": "  "})
    assert "already exists" in await tools["create_tag"].ainvoke({"name": "FOOD"})
    assert approve.asked == []


def test_tag_tools_are_in_the_tag_category_and_prompt():
    from app.services.agent.agent_service import _TOOL_CATEGORIES, SYSTEM_PROMPT

    assert {"create_tag", "rename_tag", "delete_tag"} <= _TOOL_CATEGORIES["tag"]
    assert "how many" in SYSTEM_PROMPT and "rename_tag" in SYSTEM_PROMPT


async def test_singular_wording_for_one_entry(client, auth_headers, registered_user, created_bank, test_db, approve):
    tag_id = await _make_tag(client, auth_headers, "fuel")
    await _tagged_entries(client, auth_headers, created_bank["id"], tag_id, 1)
    tools = _tools(registered_user["user_id"], test_db)
    assert "- Fuel (1 entry)" in await tools["list_tags"].ainvoke({})
    out = await tools["delete_tag"].ainvoke({"name": "fuel"})
    assert "used by 1 entry," in approve.asked[0]["summary"] and "1 entries" not in approve.asked[0]["summary"]
    assert out == "Tag 'Fuel' deleted; 1 entry no longer has it."
