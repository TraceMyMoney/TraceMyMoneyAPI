"""Characterization tests for /user-preferences."""

import pytest


async def test_get_default_preferences(client, auth_headers):
    resp = await client.get("/user-preferences/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "page_size": 5,
        "is_dark_mode": False,
        "privacy_mode_enabled": False,
        "banks_display_order": [],
    }


async def test_update_preferences(client, auth_headers):
    # Establish defaults first (as the real frontend does on load) so the
    # upsert in update_preferences has an existing document to $set onto.
    await client.get("/user-preferences/", headers=auth_headers)

    resp = await client.patch(
        "/user-preferences/update",
        json={"page_size": 25, "is_dark_mode": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"message": "SUCCESS"}

    get_resp = await client.get("/user-preferences/", headers=auth_headers)
    body = get_resp.json()
    assert body["page_size"] == 25
    assert body["is_dark_mode"] is True


async def test_update_preferences_without_prior_get(client, auth_headers):
    """
    FIXED in Phase 3 (was bug #4 in PLAN.md): under Mongo, calling update
    before any GET upserted a document missing `privacy_mode_enabled`,
    which crashed the next GET with a 500. The `user_preferences` table now
    has `privacy_mode_enabled BOOLEAN NOT NULL DEFAULT false`, so every row
    always has a value regardless of which write path created it.
    """
    resp = await client.patch(
        "/user-preferences/update",
        json={"page_size": 25, "is_dark_mode": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    get_resp = await client.get("/user-preferences/", headers=auth_headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["page_size"] == 25
    assert body["is_dark_mode"] is True
    assert body["privacy_mode_enabled"] is False
