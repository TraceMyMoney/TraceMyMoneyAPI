# StalkMyMoney MCP server

Lets Claude (claude.ai connector or any MCP client) read and record your
expenses. Stateless: each user signs in with OAuth and every tool call forwards
their own access token to the API.

## Connect from claude.ai
Settings > Connectors > Add custom connector > `https://api.stalk-my-money.in/mcp`,
sign in to StalkMyMoney when asked, click Authorize. Disconnect any time under
Profile > Connected apps.

## Tools
accounts: `list_accounts`, `create_account`, `delete_account` | tags: `list_tags` (with usage counts), `create_tag`, `rename_tag`, `delete_tag`
read: `list_expenses`, `spending_overview` | write: `add_expense`, `update_entry`, `delete_entry`, `delete_expense`
SMS inbox: `list_pending_sms`, `confirm_pending_sms`, `dismiss_pending_sms` | `whoami`

`delete_tag` is destructive and two-step: without `confirm=true` it deletes nothing and returns how many
entries would lose the tag; Claude must ask you, then call again with `confirm=true`. Tag names are saved with a
capital first letter.

`add_expense` takes account/tag **names**, a positive amount and `kind` (debit or credit),
and follows the app's rule: append to that day's expense if it exists, else create it.

## OAuth endpoints (API, root paths)
`/.well-known/oauth-authorization-server`, `/.well-known/oauth-protected-resource`
(also `/mcp/.well-known/...`), `POST /oauth/register`, `GET /oauth/authorize` (redirects to
the app's `/oauth/authorize` page), `POST /oauth/token` (PKCE S256 required), `GET /oauth/validate`.
Redirects are only allowed to hosts in `OAUTH_ALLOWED_REDIRECT_HOSTS`.

## fastmcp version (important)
Pinned exactly to `fastmcp==3.4.0` in `pyproject.toml` (extra `mcp`). The 2.x line has no
`http` transport and fails with `run() got an unexpected keyword argument 'host'`. The image
builds with `uv sync --frozen`, so after changing the pin run `uv lock` and commit `uv.lock`.

## Run locally
    uv sync --extra mcp
    SMM_API_BASE_URL=http://localhost:8000 SMM_MCP_TRANSPORT=http uv run --extra mcp python -m mcp_server.server
Needs the API running (`uv run uvicorn main:app --port 8000`) and `alembic upgrade head` applied.

## Production env (../env/.env.prod)
    API_BASE_URL=https://api.stalk-my-money.in
    FRONTEND_BASE_URL=https://app.stalk-my-money.in
