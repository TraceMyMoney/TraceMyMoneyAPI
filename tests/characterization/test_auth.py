"""Characterization tests for /register and /login."""


async def test_register_success(client):
    resp = await client.post(
        "/register",
        json={"username": "johndoe123", "email": "john@example.com", "password": "secretpass123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] == "User created successfully"
    assert "user_id" in body


async def test_register_duplicate_username(client):
    payload = {"username": "johndoe123", "email": "john@example.com", "password": "secretpass123"}
    await client.post("/register", json=payload)

    resp = await client.post(
        "/register",
        json={**payload, "email": "other@example.com"},
    )
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


async def test_register_short_username_rejected(client):
    resp = await client.post("/register", json={"username": "short", "email": "a@b.com", "password": "secretpass123"})
    assert resp.status_code == 422


async def test_register_short_password_rejected(client):
    resp = await client.post("/register", json={"username": "johndoe123", "email": "a@b.com", "password": "short"})
    assert resp.status_code == 422


async def test_login_success(client, registered_user):
    resp = await client.post(
        "/login", json={"username": registered_user["username"], "password": registered_user["password"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert body["status_code"] == 200


async def test_login_wrong_password(client, registered_user):
    resp = await client.post("/login", json={"username": registered_user["username"], "password": "wrongpass"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid username or password"


async def test_login_unknown_user(client):
    resp = await client.post("/login", json={"username": "nosuchuser", "password": "whatever123"})
    assert resp.status_code == 400


async def test_protected_endpoint_without_token(client):
    resp = await client.get("/banks/")
    assert resp.status_code == 401


async def test_protected_endpoint_with_invalid_token(client):
    resp = await client.get("/banks/", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401
