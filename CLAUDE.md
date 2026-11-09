# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Branches (start of every fix or feature)

Before changing any code, create a new branch from an up-to-date `master`:

```bash
git fetch origin && git switch -c <BRANCH-NAME> origin/master
```

Name format: `BACKEND-<TYPE>-<short-title>`, where `TYPE` is `BUG` or `FEATURE` and the title is a short lowercase hyphenated
phrase (a problem statement for a bug). Examples: `BACKEND-BUG-tag-rename-returns-500`,
`BACKEND-FEATURE-tags-crud`. If the work also touches the UI repo, use the same title there with the `FRONTEND-` prefix.

- If the working tree has uncommitted changes, do not switch silently: tell the user and ask what to do.
- Creating the branch is expected; committing and pushing are still left to the user (see below).
- Work that is only docs or config on a branch the user already named: keep using that branch.

## Commit messages (every session)

After every fix, feature, refactor, doc or config change, end the reply with exactly one line:
`[BACKEND] - <commit message>` (plain words, present tense, about 10 words, for example
`[BACKEND] - Add email outbox and background worker`). **Never `git push`, ever** (pushing to `master` deploys to production). Only run
`git commit` when the user explicitly asks, and then stage only your own changes by path (never `git add -A`). Otherwise the user
commits themselves. If a task also changed the UI, add a `[FRONTEND] - <commit message>` line.

## How to work with the user

- "Just talk", "no code" or "explain": answer only. Do not change any files.
- Design or "craft" request: make a visual draft first (an Artifact) and wait for "proceed" before writing any code.
- Concept questions: explain in simple English with a short example and no code. Keep answers short unless asked for detail.
- Do not claim certainty you do not have. Say "this is my guess" and how to test it. Say "fixed" or "found it" only when something confirms it.
- Server (EC2/AWS) problems: give a few commands at a time, say what each one does, and wait for the output before the next step. Warn before anything that deletes data (`down -v`, removing volumes).
- If a request is unclear, ask one short question instead of guessing.

## Where specs, plans and skills go

For backend-heavy work, keep the `SPEC.md`, `PLAN.md` and skills in **this repo's** `.claude/` folder: `.claude/plans/<feature>/SPEC.md`, `.claude/plans/<feature>/PLAN.md` and `.claude/skills/<name>/SKILL.md`. Never put them in a root `.claude/` folder: the project root holds only `CLAUDE.md`. If the work is mostly frontend, the files go in `TraceMyMoneyUI/.claude/` instead. A feature that touches both lives in the repo where most of its steps are (one plan, not two). Create the folders if they do not exist.

## Your role and engineering principles

Whenever you work on this backend, act as a senior principal backend engineer who knows production systems, performance and security:

- **Fast by design:** keep endpoints quick. Avoid N+1 queries (load related rows in one query or a join), select only the columns needed, paginate lists, and add or check an index for any new filter, sort or join. Never block the event loop (no sync network or heavy CPU in a request; use the async client or run it in the background).
- **Slow work goes to the background:** anything that can take more than a moment (email, PDF building, calls to external APIs) is queued (the `email_jobs` outbox pattern), never done inside the request. Make background jobs retryable and safe to run twice (idempotent).
- **Respect the small server:** production is one small box (about 1 CPU, 1GB RAM, 12GB disk) shared with other services. Watch memory (stream or page big results instead of loading them all), keep dependencies and images lean, and avoid anything that polls or scans in a tight loop.
- **Data safety first:** services always filter by `user_id`. Use transactions, and keep related writes atomic. Migrations must be safe to run on live data (add columns as nullable or with defaults, backfill, never drop data without saying so), and have a clear downgrade. Run them by hand in production after the deploy.
- **Security by default:** validate all input at the schema, never trust the client, hash secrets and tokens, use constant-time comparisons, rate-limit abusable endpoints, return the same response where a difference would leak whether an account exists, and never log secrets or personal data.
- **Right error, right place:** return the correct status code with a clear `detail`, no stack traces to the client, and log enough server-side (with context) to diagnose problems.
- **Keep the layers clean:** endpoints stay thin, business logic lives in services, schema in `tables.py`. Prefer small, readable changes that follow the existing patterns over new abstractions.
- **Prove it works:** write or update tests for behavior changes, run `uv run pytest` and `uv run ruff check .`, and say what was not verified.
- **Say what you chose:** when a trade-off matters (speed vs simplicity, safety vs convenience), state the choice and why in one or two lines.

## Every backend feature must also reach MCP and the chatbot

When you build or change a backend feature (new endpoint, new data, new action), also support it in both of these, in the same feature, not "later":

1. **MCP tool** (for claude.ai): add or update a tool in `mcp_server/server.py` that calls the API through `mcp_server/client.py` with the user's OAuth token.
   - Let users refer to things by **name**, not ids (resolve names in the tool). Validate inputs (for example dates as `YYYY-MM-DD`).
   - Write the docstring for Claude: what it does, units and sign conventions (credits are negative), and when NOT to use it. Say clearly if a tool is destructive.
   - Update the tool list in `mcp_server/README.md`.
2. **Internal chatbot tool** (for `/user/chat`): add or update a tool in `app/services/agent/tools.py` (inside `build_tools`, and add it to the returned list). If it should always be available, add it to `_ALWAYS_INCLUDED_TOOLS` in `agent_service.py` and mention it in the agent's prompt there.
   - Actions that change or delete data must go through the agent's confirmation step (the user approves before it runs).
   - Reuse the existing service methods. Do not copy business logic into the tool.

Rules for both:
- Both call the same service layer as the REST endpoint, so behavior, validation and `user_id` filtering stay identical.
- Put both in the SPEC and PLAN as their own steps, and add tests for them (`tests/`).
- If a feature truly does not make sense as an MCP tool or a chatbot tool (for example admin-only or a webhook), say so in the spec and why, instead of skipping it silently.

## Commands

```bash
# Install / sync dependencies (uv required)
uv sync

# Run dev server
uv run uvicorn main:app --reload --port 8000

# Local dev Postgres (dev-only; see PLAN.md)
docker compose -f docker-compose.dev.yml up -d
uv run alembic upgrade head

# Run all tests (requires the dev Postgres above, plus a stalk_my_money_test
# database with migrations applied - see tests/conftest.py)
uv run pytest

# Run a single test file
uv run pytest tests/characterization/test_expenses.py -v

# Build & run via Docker
docker build -t smm-api .
docker compose up -d
```

API docs available at `http://localhost:8000/docs` when running locally.

## Architecture

**This backend was migrated from MongoDB to PostgreSQL** and production runs on Postgres. See `/PLAN.md` at the repo root for the migration history and bugs. `scripts/migrate_mongo_to_pg.py` is the one-time Mongo→Postgres tool. Feature plans live in `.claude/plans/` and reusable how-tos in `.claude/skills/` **in this repo** (`TraceMyMoneyAPI/.claude/`); read the relevant ones first.

**Email** (`app/services/email/`, `app/services/account_email_service.py`): handlers only INSERT into the `email_jobs` outbox; a worker started in `main.py`'s lifespan (`EMAIL_WORKER_ENABLED`) sends through Mailgun. Tokens are in `email_tokens` (sha256-hashed, single use). Chat tool `email_expenses` queues report PDFs; `export_expenses` only downloads. **MCP/OAuth**: `mcp_server/`, `app/api/oauth.py`, `app/services/oauth_service.py`.

### Layer flow

```
main.py  →  app/api/v1/endpoints/  →  app/services/  →  app/models/ + app/db/tables.py
```

- **`main.py`** — FastAPI app, CORS middleware, lifespan (disposes the two Postgres engines on shutdown)
- **`app/api/v1/endpoints/`** — Thin route handlers; delegate all logic to services
- **`app/services/`** — All business logic; each service class takes a SQLAlchemy `AsyncSession` in `__init__`
- **`app/db/tables.py`** — SQLAlchemy Core `Table` definitions (the actual DB schema)
- **`app/db/postgres.py`** — the async `engine` and `AsyncSessionLocal` session factory
- **`app/models/`** — Pydantic models returned by services; mostly DB-shape-agnostic, with a `uuid.UUID → str` coercion on ID fields
- **`app/schemas/`** — Request/response shapes (separate from DB models)
- **`app/core/`** — Config, JWT (python-jose, HS256), password hashing (Argon2 via passlib), Groq LLM client

### Dependency injection (`app/api/deps.py`)

Services are wired through FastAPI `Depends()`. Use the pre-defined type aliases in endpoints — never instantiate services directly:

```python
CurrentUser         # Annotated[UserModel, Depends(get_current_user)]
BankServiceDep      # Annotated[BankService, Depends(get_bank_service)]
ExpenseServiceDep   # …etc.
```

`get_current_user` reads the `authorization` header (accepts both `Bearer <token>` and raw token), decodes the JWT, and fetches the user from Postgres.

### Data model

- **`banks`** / **`users`** / **`user_preferences`** — standard top-level tables
- **`expenses`** — one row per bank+date+user
- **`expense_entries`** — child rows of `expenses` (`ON DELETE CASCADE`); positive `amount` = debit (expense), negative = credit (topup); identified by `ee_id` (`ee_<uuid12>`)
- **`expense_entry_tags`** / **`expense_entry_tag_links`** — tags and their many-to-many link to entries
- All primary keys are native `UUID`, generated in Python (`uuid.uuid4()`), not DB-side
- Row-Level Security is enabled on every table with a `user_id` column (or, for `expense_entries`/`expense_entry_tag_links`, scoped via a subquery on their parent) — but the main app connects as the table owner, which bypasses RLS by default, so **services must still filter by `user_id` explicitly in every query**. RLS would only protect the read-only role `smm_chat_readonly`, which is not the table owner; that role is a leftover from the old text-to-SQL chat and nothing uses it now.

### Chatbot (`app/services/agent/`)

`/user/chat` runs a tool-using agent (`AgentChatService`), not text-to-SQL. Tools (in `tools.py`) include `add_expense`, `export_expenses` (download only) and `email_expenses` (emails a PDF, only when the user explicitly asks for email). An admin enables the chatbot per user; others get a 403. The old text-to-SQL guardrails (`smm_chat_readonly` role, RLS, `sqlglot`) are leftovers; nothing in `app/` uses them now, and new tables still `REVOKE` from that role.

### LLM

`app/core/llm.py` builds the chat model (Groq by default; admins can switch provider). Used by the agent (`app/services/agent/agent_service.py`), SMS parsing (`app/services/sms_ai.py`) and the admin settings. Requires `GROQ_API_KEY` and `GROQ_MODEL_NAME`.

## Environment (`.env`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Main app's Postgres connection string (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | JWT signing key |
| `ALGORITHM` | JWT algorithm (default HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL |
| `GROQ_API_KEY` | Groq LLM key |
| `GROQ_MODEL_NAME` | Model identifier |
| `BACKEND_CORS_ORIGINS` | JSON array or comma-separated list |
| `MAILGUN_API_KEY` / `MAILGUN_URI` / `MAILGUN_FROM_ADDR` | Mailgun sending; all empty = console backend (logs the email, sends nothing) |
| `EMAIL_FROM_NAME` / `EMAIL_WORKER_ENABLED` | Sender display name; turn the background worker off (tests) |
| `API_BASE_URL` / `FRONTEND_BASE_URL` | Public URLs for email links and the OAuth redirect (set in `docker-compose.yml` in prod; default localhost) |
| `MONGODB_URL` / `MONGODB_DB_NAME` | Only needed to run `scripts/migrate_mongo_to_pg.py`; unused by the running app otherwise |

## CI/CD

`.github/workflows/deploy_on_ec2.yml`: every push builds a versioned Docker image (`<branch>_<sha>`); merges to `master` tag as `latest` and SSH-deploy to EC2 via `docker compose up -d`, which reads `env_file: ../env/.env.prod` on the EC2 host. Tests are commented out in CI — run `uv run pytest` locally before pushing to `master`.

**Migrations are not run by the deploy.** After deploying code that adds a migration, run it by hand on the EC2 box: `docker exec stalkmymoney_api uv run alembic upgrade head` (check with `... alembic current`). Deploying code before its migration makes the API fail with "relation/column does not exist". Production compose runs uvicorn without `--reload`.
