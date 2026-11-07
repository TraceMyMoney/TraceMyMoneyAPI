"""Characterization tests for /entry-tags."""

import pytest


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
