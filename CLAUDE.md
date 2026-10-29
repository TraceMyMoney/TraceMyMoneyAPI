# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

**This backend was migrated from MongoDB to PostgreSQL.** See `/PLAN.md` at the repo root for the full migration history, every bug found/fixed along the way, and what's still outstanding (the Phase 6 cutover and a from-scratch migration run against real production data). `scripts/migrate_mongo_to_pg.py` is the one-time Mongo→Postgres data migration tool; it stays in the repo until Phase 6 is complete.

### Layer flow

```
main.py  →  app/api/v1/endpoints/  →  app/services/  →  app/models/ + app/db/tables.py
```

- **`main.py`** — FastAPI app, CORS middleware, lifespan (disposes the two Postgres engines on shutdown)
- **`app/api/v1/endpoints/`** — Thin route handlers; delegate all logic to services
- **`app/services/`** — All business logic; each service class takes a SQLAlchemy `AsyncSession` in `__init__`
- **`app/db/tables.py`** — SQLAlchemy Core `Table` definitions (the actual DB schema)
- **`app/db/postgres.py`** — the two engines: `engine`/`AsyncSessionLocal` (main app) and `chat_engine` (restricted read-only role for the Text-to-SQL chat feature)
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
- Row-Level Security is enabled on every table with a `user_id` column (or, for `expense_entries`/`expense_entry_tag_links`, scoped via a subquery on their parent) — but the main app connects as the table owner, which bypasses RLS by default, so **services must still filter by `user_id` explicitly in every query**. RLS is the enforcement backstop for the Text-to-SQL chat role specifically, which is *not* the table owner.

### Text-to-SQL chat (`app/services/chat/`)

`/user/chat` turns a natural-language question into a single read-only SQL `SELECT`, with layered guardrails (see PLAN.md Phase 4 for the full rationale): a dedicated `smm_chat_readonly` Postgres role with no write grants and no access at all to `users`; RLS scoping every row to `current_setting('app.user_id')`; `sqlglot` parsing that rejects anything but one `SELECT` against an explicit table allowlist; a `statement_timeout`; and a transaction that's always rolled back regardless of outcome.

### LLM

`app/core/llm.py` exposes a module-level `LLM = ChatGroq(...)` singleton. Used only in `app/services/chat/chat_service.py`. Requires `GROQ_API_KEY` and `GROQ_MODEL_NAME` env vars.

## Environment (`.env`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Main app's Postgres connection string (`postgresql+asyncpg://...`) |
| `CHAT_DATABASE_URL` | Restricted read-only role's connection string, for the chat feature |
| `SECRET_KEY` | JWT signing key |
| `ALGORITHM` | JWT algorithm (default HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL |
| `GROQ_API_KEY` | Groq LLM key |
| `GROQ_MODEL_NAME` | Model identifier |
| `BACKEND_CORS_ORIGINS` | JSON array or comma-separated list |
| `MONGODB_URL` / `MONGODB_DB_NAME` | Only needed to run `scripts/migrate_mongo_to_pg.py`; unused by the running app otherwise |

## CI/CD

`.github/workflows/deploy_on_ec2.yml`: every push builds a versioned Docker image (`<branch>_<sha>`); merges to `master` tag as `latest` and SSH-deploy to EC2 via `docker compose up -d`, which reads `env_file: ../env/.env.prod` on the EC2 host. Tests are commented out in CI — run `uv run pytest` locally before pushing to `master`.

**Before the production cutover** (PLAN.md Phase 6), the EC2 host's `../env/.env.prod` needs `DATABASE_URL`/`CHAT_DATABASE_URL` added, and a production Postgres instance needs to exist and have both Alembic migrations applied — this isn't automated by anything in this repo and hasn't been done yet.
