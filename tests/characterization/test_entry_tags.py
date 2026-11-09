"""Characterization tests for /entry-tags."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.entry_tag import EntryTagCreate, EntryTagUpdate, normalize_tag_name
from app.services.entry_tag_service import EntryTagService


async def test_get_entry_tags_empty(client, auth_headers):
    resp = await client.get("/entry-tags/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"entry_tags": []}


async def test_create_entry_tag(client, auth_headers):
    resp = await client.post("/entry-tags/create", json={"name": "Groceries"}, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] == "Tag created successfully"
    assert "tag_id" in body


async def test_get_entry_tags_after_create(client, auth_headers):
    await client.post("/entry-tags/create", json={"name": "Groceries"}, headers=auth_headers)

    resp = await client.get("/entry-tags/", headers=auth_headers)
    tags = resp.json()["entry_tags"]
    assert len(tags) == 1
    assert tags[0]["name"] == "Groceries"
    assert "id" in tags[0]
    assert "created_at" in tags[0]


async def test_create_duplicate_tag_name_rejected(client, auth_headers):
    await client.post("/entry-tags/create", json={"name": "Groceries"}, headers=auth_headers)
    resp = await client.post("/entry-tags/create", json={"name": "Groceries"}, headers=auth_headers)
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


# ---- Step 1 of .claude/plans/tags-crud: naming rule, counts, rename, delete (service level) ----


@pytest.fixture
def tag_service(test_db):
    return EntryTagService(test_db)


@pytest.mark.parametrize(
    "typed, saved",
    [
        ("food", "Food"),
        ("rent and bills", "Rent and bills"),
        ("EMI", "EMI"),
        ("upi", "Upi"),
        ("  rent    and  bills ", "Rent and bills"),
        ("fooD", "FooD"),
    ],
)
def test_normalize_tag_name(typed, saved):
    assert normalize_tag_name(typed) == saved


def test_schema_rejects_empty_and_too_long_names():
    with pytest.raises(ValidationError):
        EntryTagCreate(name="   ")
    with pytest.raises(ValidationError):
        EntryTagCreate(name="x" * 51)
    assert EntryTagCreate(name="x" * 50).name == "X" + "x" * 49


async def test_create_saves_capitalized_name_via_api(client, auth_headers):
    await client.post("/entry-tags/create", json={"name": "  groceries  "}, headers=auth_headers)
    tags = (await client.get("/entry-tags/", headers=auth_headers)).json()["entry_tags"]
    assert [t["name"] for t in tags] == ["Groceries"]


async def test_create_duplicate_is_case_insensitive(client, auth_headers):
    await client.post("/entry-tags/create", json={"name": "Food"}, headers=auth_headers)
    resp = await client.post("/entry-tags/create", json={"name": "fOOD"}, headers=auth_headers)
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


async def _make_tag(tag_service, user_id, name):
    return await tag_service.create_tag(user_id, EntryTagCreate(name=name))


async def _tag_entries(client, auth_headers, bank_id, tag_id, count):
    resp = await client.post(
        "/expenses/create",
        json={
            "bank_id": bank_id,
            "expenses": [
                {"amount": 10.0 + i, "description": f"e{i}", "entry_tags": [tag_id], "type": "expense"}
                for i in range(count)
            ],
            "created_at": "01/01/2026 00:00",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


async def test_get_tags_has_counts_and_is_sorted_by_name(
    client, auth_headers, registered_user, created_bank, tag_service
):
    uid = registered_user["user_id"]
    await _make_tag(tag_service, uid, "zebra")
    used = await _make_tag(tag_service, uid, "apple")
    await _make_tag(tag_service, uid, "Mango")
    await _tag_entries(client, auth_headers, created_bank["id"], used.id, 2)

    tags = await tag_service.get_tags(uid)
    assert [(t.name, t.entry_count) for t in tags] == [("Apple", 2), ("Mango", 0), ("Zebra", 0)]

    listed = (await client.get("/entry-tags/", headers=auth_headers)).json()["entry_tags"]
    assert [t["name"] for t in listed] == ["Apple", "Mango", "Zebra"]


async def test_get_tag_by_name_ignores_case_and_spaces(registered_user, tag_service):
    uid = registered_user["user_id"]
    created = await _make_tag(tag_service, uid, "rent and bills")
    found = await tag_service.get_tag_by_name(uid, "  RENT   and BILLS ")
    assert found is not None and found.id == created.id
    assert await tag_service.get_tag_by_name(uid, "nope") is None
    assert await tag_service.get_tag_by_name(uid, "   ") is None


async def test_rename_ok_same_name_and_case_only_change(registered_user, tag_service):
    uid = registered_user["user_id"]
    tag = await _make_tag(tag_service, uid, "food")

    renamed = await tag_service.update_tag(uid, tag.id, EntryTagUpdate(name="groceries"))
    assert renamed.name == "Groceries" and renamed.id == tag.id

    same = await tag_service.update_tag(uid, tag.id, EntryTagUpdate(name="Groceries"))
    assert same.name == "Groceries"

    case_only = await tag_service.update_tag(uid, tag.id, EntryTagUpdate(name="GROCERIES"))
    assert case_only.name == "GROCERIES"


async def test_rename_to_existing_name_raises(registered_user, tag_service):
    uid = registered_user["user_id"]
    await _make_tag(tag_service, uid, "food")
    other = await _make_tag(tag_service, uid, "rent")
    with pytest.raises(ValueError, match="already exists"):
        await tag_service.update_tag(uid, other.id, EntryTagUpdate(name="FOOD"))
    assert (await tag_service.get_tag_by_id(uid, other.id)).name == "Rent"


async def test_other_users_tag_is_not_found(registered_user, tag_service):
    uid = registered_user["user_id"]
    tag = await _make_tag(tag_service, uid, "food")
    stranger = str(uuid.uuid4())

    assert await tag_service.get_tag_by_id(stranger, tag.id) is None
    assert await tag_service.update_tag(stranger, tag.id, EntryTagUpdate(name="x")) is None
    assert await tag_service.delete_tag(stranger, tag.id) is None
    assert await tag_service.get_tag_by_id(uid, tag.id) is not None  # untouched
    assert await tag_service.update_tag(uid, "not-a-uuid", EntryTagUpdate(name="x")) is None
    assert await tag_service.delete_tag(uid, "not-a-uuid") is None


async def test_delete_unused_tag_returns_zero(registered_user, tag_service):
    uid = registered_user["user_id"]
    tag = await _make_tag(tag_service, uid, "gifts")
    assert await tag_service.delete_tag(uid, tag.id) == 0
    assert await tag_service.get_tag_by_id(uid, tag.id) is None


async def test_delete_removes_links_keeps_entries_and_cleans_excluded_tags(
    client, auth_headers, registered_user, created_bank, tag_service
):
    uid = registered_user["user_id"]
    doomed = await _make_tag(tag_service, uid, "fuel")
    keeper = await _make_tag(tag_service, uid, "travel")
    await _tag_entries(client, auth_headers, created_bank["id"], doomed.id, 3)
    await client.patch(
        "/user-preferences/update", json={"default_excluded_tags": [doomed.id, keeper.id]}, headers=auth_headers
    )

    assert await tag_service.delete_tag(uid, doomed.id) == 3

    assert [t.name for t in await tag_service.get_tags(uid)] == ["Travel"]
    prefs = (await client.get("/user-preferences/", headers=auth_headers)).json()
    assert prefs["default_excluded_tags"] == [keeper.id]
    expenses = (await client.get("/expenses/", headers=auth_headers)).json()
    assert "e0" in str(expenses) and "e2" in str(expenses)  # entries survive


# ---- Step 2 of .claude/plans/tags-crud: PATCH / DELETE endpoints ----


async def _create_via_api(client, auth_headers, name):
    resp = await client.post("/entry-tags/create", json={"name": name}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["tag_id"]


async def test_create_response_returns_saved_name(client, auth_headers):
    resp = await client.post("/entry-tags/create", json={"name": "food"}, headers=auth_headers)
    assert resp.json()["name"] == "Food"


async def test_get_entry_tags_includes_entry_count(client, auth_headers, created_bank):
    tag_id = await _create_via_api(client, auth_headers, "fuel")
    await _tag_entries(client, auth_headers, created_bank["id"], tag_id, 2)
    tags = (await client.get("/entry-tags/", headers=auth_headers)).json()["entry_tags"]
    assert tags[0]["entry_count"] == 2


async def test_rename_tag_endpoint(client, auth_headers):
    tag_id = await _create_via_api(client, auth_headers, "food")
    resp = await client.patch(f"/entry-tags/{tag_id}", json={"name": "  groceries "}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tag"]["name"] == "Groceries"
    assert resp.json()["tag"]["id"] == tag_id
    tags = (await client.get("/entry-tags/", headers=auth_headers)).json()["entry_tags"]
    assert [t["name"] for t in tags] == ["Groceries"]


async def test_rename_tag_to_same_name_is_ok(client, auth_headers):
    tag_id = await _create_via_api(client, auth_headers, "food")
    resp = await client.patch(f"/entry-tags/{tag_id}", json={"name": "Food"}, headers=auth_headers)
    assert resp.status_code == 200


async def test_rename_tag_duplicate_is_400_not_500(client, auth_headers):
    await _create_via_api(client, auth_headers, "food")
    other = await _create_via_api(client, auth_headers, "rent")
    resp = await client.patch(f"/entry-tags/{other}", json={"name": "FOOD"}, headers=auth_headers)
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


async def test_rename_tag_invalid_name_is_422(client, auth_headers):
    tag_id = await _create_via_api(client, auth_headers, "food")
    assert (await client.patch(f"/entry-tags/{tag_id}", json={"name": "   "}, headers=auth_headers)).status_code == 422
    assert (
        await client.patch(f"/entry-tags/{tag_id}", json={"name": "x" * 51}, headers=auth_headers)
    ).status_code == 422
    assert (await client.patch(f"/entry-tags/{tag_id}", json={}, headers=auth_headers)).status_code == 422


async def test_rename_and_delete_unknown_or_bad_id_are_404(client, auth_headers):
    for tag_id in (str(uuid.uuid4()), "not-a-uuid"):
        assert (
            await client.patch(f"/entry-tags/{tag_id}", json={"name": "x"}, headers=auth_headers)
        ).status_code == 404
        assert (await client.delete(f"/entry-tags/{tag_id}", headers=auth_headers)).status_code == 404


async def test_delete_tag_endpoint_reports_untagged_count(client, auth_headers, created_bank):
    tag_id = await _create_via_api(client, auth_headers, "fuel")
    await _tag_entries(client, auth_headers, created_bank["id"], tag_id, 3)
    resp = await client.delete(f"/entry-tags/{tag_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["entries_untagged"] == 3
    assert (await client.get("/entry-tags/", headers=auth_headers)).json() == {"entry_tags": []}
    assert (await client.delete(f"/entry-tags/{tag_id}", headers=auth_headers)).status_code == 404


async def test_tag_endpoints_do_not_touch_other_users_tags(client, auth_headers, test_db):
    tag_id = await _create_via_api(client, auth_headers, "food")

    other = {"username": "otheruser", "email": "other@example.com", "password": "testpass123"}
    assert (await client.post("/register", json=other)).status_code == 200
    from sqlalchemy import text

    await test_db.execute(text("UPDATE users SET email_verified_at = now() WHERE username = 'otheruser'"))
    await test_db.commit()
    login = await client.post("/login", json={"username": "otheruser", "password": "testpass123"})
    other_headers = {"Authorization": f"Bearer {login.json()['token']}"}

    assert (
        await client.patch(f"/entry-tags/{tag_id}", json={"name": "Hack"}, headers=other_headers)
    ).status_code == 404
    assert (await client.delete(f"/entry-tags/{tag_id}", headers=other_headers)).status_code == 404
    mine = (await client.get("/entry-tags/", headers=auth_headers)).json()["entry_tags"]
    assert [t["name"] for t in mine] == ["Food"]
    assert (await client.get("/entry-tags/", headers=other_headers)).json() == {"entry_tags": []}


async def test_tag_endpoints_require_auth(client):
    tag_id = str(uuid.uuid4())
    assert (await client.patch(f"/entry-tags/{tag_id}", json={"name": "x"})).status_code in (401, 403, 422)
    assert (await client.delete(f"/entry-tags/{tag_id}")).status_code in (401, 403, 422)
