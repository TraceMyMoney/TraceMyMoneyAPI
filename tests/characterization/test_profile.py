"""Profile: view / edit username + email, change password; short ingest token."""


async def test_get_profile(client, auth_headers):
    body = (await client.get("/profile/", headers=auth_headers)).json()
    assert body["username"] == "characterization"
    assert body["email"] == "characterization@example.com"


async def test_update_username_returns_fresh_tokens(client, auth_headers):
    resp = await client.patch("/profile/", json={"username": "renamed_user"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "renamed_user" and body["token"] and body["refresh_token"]
    login = await client.post("/login", json={"username": "renamed_user", "password": "testpass123"})
    assert login.status_code == 200


async def test_update_rejects_taken_username_and_short_one(client, auth_headers):
    other = {"username": "someone_else", "email": "other@example.com", "password": "testpass123"}
    assert (await client.post("/register", json=other)).status_code == 200
    taken = await client.patch("/profile/", json={"username": "someone_else"}, headers=auth_headers)
    assert taken.status_code == 400 and "taken" in taken.json()["detail"]
    email_taken = await client.patch("/profile/", json={"email": "other@example.com"}, headers=auth_headers)
    assert email_taken.status_code == 400
    assert (await client.patch("/profile/", json={"username": "short"}, headers=auth_headers)).status_code == 422


async def test_change_password(client, auth_headers):
    wrong = await client.post(
        "/profile/password", json={"current_password": "nope", "new_password": "newpass1234"}, headers=auth_headers
    )
    assert wrong.status_code == 400
    ok = await client.post(
        "/profile/password",
        json={"current_password": "testpass123", "new_password": "newpass1234"},
        headers=auth_headers,
    )
    assert ok.status_code == 200
    assert (
        await client.post("/login", json={"username": "characterization", "password": "newpass1234"})
    ).status_code == 200


async def test_ingest_token_is_short(client, auth_headers):
    token = (await client.post("/ingest/token", headers=auth_headers)).json()["token"]
    assert token.startswith("smm_") and len(token) == 20
