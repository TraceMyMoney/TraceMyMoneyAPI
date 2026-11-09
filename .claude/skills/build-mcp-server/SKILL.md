---
name: build-mcp-server
description: Build a remote MCP server (FastMCP 3.x) with OAuth so claude.ai can connect to an existing web app as a connector. Use when asked to add an MCP server, a Claude connector, or "talk to my app from claude.ai". Based on the working StalkMyMoney and obsidian-clone implementations.
---

# Build an MCP server + OAuth for claude.ai

Reference implementations (read these first, copy their shape):
- `TraceMyMoneyAPI/mcp_server/` + `app/api/oauth.py` + `app/services/oauth_service.py` (StalkMyMoney)
- `~/projects/obsidian-clone` backend (the original)

## 0. Hard rules (these cost hours before)

- **Pin `fastmcp==3.4.0` exactly.** 2.x has no http transport and fails with
  `TypeError: run() got an unexpected keyword argument 'host'`.
- After any pin change run `uv lock` and commit `uv.lock`. Docker builds use
  `uv sync --frozen`, so the lock decides what gets installed.
- Put `python-multipart` in the base dependencies. `/oauth/token` takes form data and the
  production image does not install extras.
- Name the compose service uniquely (`smm_mcp`, not `mcp`): `edge-network` is shared
  between projects and a bare name clashes.

## 1. Architecture

The MCP server is a small stateless HTTP client of the app's own API. No DB access.

- `TokenVerifier` calls `GET /oauth/validate` on the API with the bearer token.
- Each tool receives the token via `auth: AccessToken = CurrentAccessToken()` and
  forwards it to the API. The API stays the single source of truth for auth and data.
- The API's `get_current_user` accepts either a normal JWT or an OAuth opaque token
  (fallback lookup in `oauth_tokens`, reject disabled users).
- Run with `mcp.run(transport="http", host=..., port=..., path="/mcp")`.

## 2. OAuth the API must provide (claude.ai expects all of it)

- RFC 8414 authorization-server metadata: `/.well-known/oauth-authorization-server`
- RFC 9728 protected-resource metadata: `/.well-known/oauth-protected-resource`
  (also served under `/mcp/.well-known/...`, claude.ai asks there)
- RFC 7591 dynamic client registration: `POST /oauth/register`
- `GET /oauth/authorize`: validate, then 302 to the frontend approval page
- `POST /oauth/token`: authorization-code grant, **PKCE S256 mandatory**
- Codes: 5 minutes, single use (atomic `UPDATE ... RETURNING`)
- Access tokens: 90 days, store only the sha256 hash
- **Redirect-host allowlist** (claude.ai, claude.com, localhost). DCR is open, so without
  this anyone can register a client that sends the user's approval to their own site.
- Revocation UI (Profile > Connected apps)

## 3. Frontend approval page

- Needs the user's normal session. Do not put the JWT in a form field.
- Flow: API redirects to `<frontend>/oauth/authorize?...` -> page calls
  `GET /oauth/authorize/info`, then `POST /oauth/authorize/decision` -> `{redirect_url}`
  -> browser goes to Claude.
- If the frontend is a static host (Surge), the build needs a SPA fallback
  (`cp dist/index.html dist/200.html`) or the deep path 404s.

## 4. Tool design lessons

- Let the user refer to things by **name**, not ids (resolve names in the tool, create
  missing ones where harmless).
- Validate inputs in the tool (dates as YYYY-MM-DD) because the API may silently accept bad
  values.
- Write docstrings for Claude: say what the tool does, units, sign conventions
  (credits negative), and when NOT to use it.
- Destructive tools (delete_*) should say so in the docstring so Claude confirms first.
- Check the real API response keys (StalkMyMoney returns `id`, not `_id`).

## 5. Deployment checklist

1. Set **public URLs** for the API container: `API_BASE_URL` and `FRONTEND_BASE_URL`.
   If missing, the authorize redirect goes to `http://localhost:5173` (this happened).
2. Run the Alembic migration for the OAuth tables on the production DB.
3. Add the MCP service to `docker-compose.yml` on `edge-network`;
   `SMM_API_BASE_URL` points at the API **container name**, not localhost.
4. nginx gateway: route `/mcp` and `/mcp/.well-known/` to the MCP service with
   `proxy_buffering off`, `proxy_http_version 1.1`, `Connection ""`, long read timeouts
   (Streamable HTTP breaks otherwise). Reload nginx.
5. Deploy the frontend (the approval page must exist in production).
6. claude.ai > Settings > Connectors > add `https://<api-domain>/mcp`, sign in, Authorize.
7. If it fails: `curl https://<api-domain>/mcp/.well-known/oauth-protected-resource` must
   return JSON.

## 6. How to verify before saying done

- Unit/characterization tests for the OAuth endpoints (PKCE, single-use code, expiry,
  redirect allowlist, revoke).
- A live end-to-end run with a real MCP client: register, authorize, token, call tools,
  revoke, then confirm the revoked and missing tokens are rejected.
- Build the MCP Docker image with the frozen lock and confirm `fastmcp 3.4.0` inside it.

## 7. Work habits that kept this smooth

- Don't commit unless asked; end with a commit message in the project's format.
- Local backend runs with `uv run uvicorn`; Docker only on EC2.
- Never read production credentials.
