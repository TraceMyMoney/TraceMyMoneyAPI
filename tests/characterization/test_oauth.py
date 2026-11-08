"""Claude connector OAuth: registration, authorize (PKCE), token, use, revoke."""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

REDIRECT = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


async def _register(client, redirect=REDIRECT):
    return await client.post("/oauth/register", json={"client_name": "Claude", "redirect_uris": [redirect]})


async def _authorize(client, headers, approve=True):
    return await client.post(
        "/oauth/authorize/decision",
        json={
            "client_id": "claude",
            "redirect_uri": REDIRECT,
            "state": "xyz",
            "code_challenge": CHALLENGE,
            "approve": approve,
        },
        headers=headers,
    )


async def _token(client, code, verifier=VERIFIER):
    return await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": "claude",
            "code_verifier": verifier,
        },
    )


async def _connect(client, headers):
    assert (await _register(client)).status_code == 201
    url = (await _authorize(client, headers)).json()["redirect_url"]
    code = parse_qs(urlparse(url).query)["code"][0]
    resp = await _token(client, code)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def test_metadata_and_resource_documents(client):
    meta = (await client.get("/.well-known/oauth-authorization-server")).json()
    assert meta["token_endpoint"].endswith("/oauth/token")
    assert meta["code_challenge_methods_supported"] == ["S256"]
    res = (await client.get("/mcp/.well-known/oauth-protected-resource")).json()
    assert res["resource"].endswith("/mcp") and res["authorization_servers"]


async def test_register_rejects_foreign_redirect_hosts(client):
    assert (await _register(client, "https://evil.example.com/cb")).status_code == 400
    assert (await _register(client, "http://claude.ai/cb")).status_code == 400
    assert (await _register(client)).status_code == 201


async def test_authorize_redirects_browser_to_app(client):
    resp = await client.get(
        "/oauth/authorize",
        params={"client_id": "claude", "redirect_uri": REDIRECT, "state": "s", "code_challenge": CHALLENGE},
        follow_redirects=False,
    )
    assert resp.status_code == 302 and "/oauth/authorize?" in resp.headers["location"]


async def test_full_flow_token_works_on_api_and_can_be_revoked(client, auth_headers):
    token = await _connect(client, auth_headers)
    bearer = {"Authorization": f"Bearer {token}"}

    assert (await client.get("/banks/", headers=bearer)).status_code == 200
    who = await client.get("/oauth/validate", headers=bearer)
    assert who.status_code == 200 and who.json()["username"] == "characterization"

    conns = (await client.get("/oauth/connections", headers=auth_headers)).json()
    assert len(conns) == 1 and conns[0]["client_name"] == "Claude"
    assert (await client.delete(f"/oauth/connections/{conns[0]['id']}", headers=auth_headers)).status_code == 200

    assert (await client.get("/banks/", headers=bearer)).status_code == 401
    assert (await client.get("/oauth/validate", headers=bearer)).status_code == 401


async def test_code_is_single_use_and_pkce_enforced(client, auth_headers):
    assert (await _register(client)).status_code == 201
    code = parse_qs(urlparse((await _authorize(client, auth_headers)).json()["redirect_url"]).query)["code"][0]
    assert (await _token(client, code, verifier="wrong" * 10)).status_code == 400  # burns the code
    assert (await _token(client, code)).status_code == 400  # already used

    code2 = parse_qs(urlparse((await _authorize(client, auth_headers)).json()["redirect_url"]).query)["code"][0]
    assert (await _token(client, code2)).status_code == 200
    assert (await _token(client, code2)).status_code == 400


async def test_deny_redirects_with_access_denied(client, auth_headers):
    assert (await _register(client)).status_code == 201
    url = (await _authorize(client, auth_headers, approve=False)).json()["redirect_url"]
    assert parse_qs(urlparse(url).query)["error"] == ["access_denied"]


async def test_authorize_decision_requires_login_and_known_client(client, auth_headers):
    assert (await _authorize(client, {})).status_code == 401
    assert (await _authorize(client, auth_headers)).status_code == 400  # client never registered


async def test_garbage_bearer_is_rejected(client):
    assert (await client.get("/banks/", headers={"Authorization": "Bearer not-a-real-token"})).status_code == 401
