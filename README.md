# TraceMyMoney API

![Python](https://img.shields.io/badge/python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791) ![uv](https://img.shields.io/badge/packages-uv-purple)

The FastAPI + PostgreSQL backend of **StalkMyMoney**, a personal finance tracker. It stores accounts,
expenses and tags, and adds an AI chatbot, bank-SMS import, background email and a Claude connector on top.

- Production API: `https://api.stalk-my-money.in`
- Web app (separate repo): [`TraceMyMoneyUI`](https://github.com/TraceMyMoney/TraceMyMoneyUI), live at `https://app.stalk-my-money.in`

## Contents

1. [Features](#features) 2. [Architecture](#architecture) 3. [Getting started](#getting-started)
4. [API documentation](#api-documentation) 5. [Deployment and configuration](#deployment-and-configuration)
6. [Development workflow](#development-workflow)

---

## Features

- **Money tracking:** accounts (banks), daily expenses with many entries (debits and top-ups), tags,
  advanced search, graphs and an analytics overview.
- **AI chatbot** (`POST /user/chat`): a tool-using agent. It adds expenses, answers questions about your
  spending, and can **download** a PDF/Excel report or **email** it. It emails only when the user explicitly
  asks for email. An admin enables the chatbot per user.
- **Email that never blocks a request:** signup confirmation, password reset and emailed reports go through
  a Postgres outbox and a background worker (Mailgun).
- **Bank SMS import:** a webhook turns bank SMS into expenses; unclear ones wait in an inbox for review.
- **Claude connector:** an MCP server plus OAuth, so claude.ai can read and record your expenses.
- **Admin tools:** user management, chatbot access, AI model and provider settings, feature flags.

**How it differs from typical trackers:** you can talk to it (chat or Claude), it imports expenses from SMS
on its own, and it never makes a user wait for email.

## Architecture

### High-level diagram

```mermaid
flowchart LR
    Browser["Web app (React)"] --> GW["nginx gateway<br/>TLS + routing"]
    Claude["claude.ai connector"] --> GW
    GW -->|"/mcp"| MCP["MCP server<br/>(FastMCP, stateless)"]
    GW --> API["FastAPI API"]
    MCP -->|"user's OAuth token"| API
    API --> Services["Services<br/>(business logic)"]
    Services --> PG[("PostgreSQL")]
    Services -->|"INSERT job"| Outbox[("email_jobs outbox")]
    Worker["Email worker<br/>(in the API process)"] -->|"claims jobs"| Outbox
    Worker --> Mailgun["Mailgun HTTP API"]
    Services --> LLM["LLM providers<br/>(Groq / OpenAI / Anthropic ...)"]
```

### Request flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as nginx gateway
    participant A as FastAPI endpoint
    participant D as Dependencies
    participant S as Service
    participant P as PostgreSQL
    C->>G: HTTPS request + Bearer token
    G->>A: forward (CORS applied)
    A->>D: resolve current user
    D->>P: load user from the token
    D-->>A: user + service instance
    A->>S: call business logic
    S->>P: SQL (always filtered by user_id)
    P-->>S: rows
    S-->>A: models
    A-->>C: JSON response
    Note over S,P: Slow work such as email is only queued<br/>(INSERT into email_jobs). A worker sends it later.
```

1. The client sends a request to the nginx gateway, which forwards it to the API (or `/mcp` to the MCP server).
2. FastAPI applies CORS, then routes to a thin **endpoint** function in `app/api/v1/endpoints/`.
3. Dependencies (`app/api/deps.py`) read the `authorization` header, decode the JWT (or an OAuth token), load
   the user and build the service.
4. The **service** runs the business logic with SQLAlchemy (async) against PostgreSQL and returns models.
5. The endpoint returns JSON. Anything slow (sending email) is only queued here and done later by the worker.

### Background email flow

```mermaid
sequenceDiagram
    participant U as User
    participant A as API handler
    participant O as email_jobs table
    participant W as Worker
    participant M as Mailgun
    U->>A: Sign up / forgot password / "email me my report"
    A->>O: INSERT job (a few ms)
    A-->>U: Response right away
    W->>O: Claim job (FOR UPDATE SKIP LOCKED)
    W->>M: Send email (PDF built now for reports)
    alt sent
        W->>O: status = sent, payload scrubbed
    else temporary error (5xx, 429, network)
        W->>O: retry later (1m, 5m, 30m, 2h; max 5 tries)
    else permanent error (other 4xx)
        W->>O: status = failed
    end
    M-->>U: Email arrives
```

### Data model

```mermaid
erDiagram
    users ||--o{ banks : owns
    users ||--o{ expense_entry_tags : owns
    users ||--|| user_preferences : has
    users ||--o{ email_tokens : "verify / reset"
    users ||--o{ email_jobs : "queued mail"
    banks ||--o{ expenses : "one row per bank + day"
    expenses ||--o{ expense_entries : "ON DELETE CASCADE"
    expense_entries }o--o{ expense_entry_tags : "expense_entry_tag_links"
    expenses {
        uuid id PK
        uuid user_id FK
        uuid bank_id FK
        date day
        numeric expense_total
    }
    expense_entries {
        uuid id PK
        string ee_id
        uuid expense_id FK
        numeric amount "positive = debit, negative = top-up"
        string description
    }
    email_jobs {
        uuid id PK
        string kind
        string status "pending, sending, sent, failed"
        int attempts
        timestamp run_after
    }
```

### Folder structure

```
main.py                    FastAPI app, CORS, lifespan (starts and stops the email worker)
app/api/v1/endpoints/      Route handlers (thin, no business logic)
app/api/oauth.py           OAuth endpoints for the Claude connector (root paths)
app/api/deps.py            Dependency injection: current user, services
app/services/              Business logic, one class per area, each takes an AsyncSession
app/services/agent/        Chatbot agent, its tools, report and PDF building
app/services/email/        Mailgun sender, templates, outbox, worker, tokens
app/db/tables.py           SQLAlchemy Core table definitions (the schema)
app/db/postgres.py         Async engine and session factory
app/models/, app/schemas/  Pydantic models (service results) and request/response shapes
app/core/                  Config, JWT, password hashing, rate limiting, LLM clients
alembic/                   Database migrations
mcp_server/                MCP server for the Claude connector
tests/                     pytest suite
```

### Key design decisions

- **Postgres outbox for email.** Handlers insert a row in a few milliseconds; a worker claims rows with
  `FOR UPDATE SKIP LOCKED`, retries with backoff, and survives restarts. No Redis or Celery to run.
- **Services always filter by `user_id`.** The app connects as the table owner, which bypasses row-level
  security, so every query is scoped explicitly. RLS is a backstop for the read-only role.
- **Tokens are stored hashed** (verify/reset tokens and OAuth tokens), single use, with short lifetimes.
- **Anti-enumeration:** forgot-password and resend-verification always return the same message.
- **Native UUID primary keys generated in Python.**
- **MCP server is stateless.** It forwards each user's own OAuth token to the API, so the API stays the single
  place for auth and data.
- **Chatbot actions are explicit.** Downloading and emailing are separate tools, so email is sent only on request.

### Tech stack

| Area | Choice |
|---|---|
| Language / runtime | Python 3.11 |
| Web framework | FastAPI 0.135, Uvicorn 0.44, Pydantic 2.12 |
| Database | PostgreSQL 16, SQLAlchemy 2.0 (async), asyncpg 0.32, Alembic 1.20 |
| Auth | JWT (python-jose, HS256), Argon2 password hashing, OAuth 2.0 + PKCE for the connector |
| AI | LangChain 1.4 (Groq, OpenAI, Anthropic, OpenRouter providers) |
| Email | Mailgun HTTP API via httpx |
| Reports | reportlab (PDF) |
| MCP | FastMCP 3.4.0 (pinned exactly) |
| Packages | uv |
| Tests / lint | pytest 9 (asyncio), ruff |

### Patterns used

Layered architecture (endpoint, service, table), dependency injection, outbox pattern for background work,
per-user data scoping, and thin stateless adapters (the MCP server).

---

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/): `curl -LsSf https://astral.sh/uv/install.sh | sh` (it also installs Python).
- Docker, for the local PostgreSQL container (or to run the API itself in a container).
- A Groq (or other LLM) API key, only if you want the chatbot to work.

### Environment variables

Read from the environment or a `.env` file in this folder. All have local defaults unless marked **needed**.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db`. Default matches the dev container below |
| `SECRET_KEY` | JWT signing key. **Set a real one outside local dev** |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes (default 30 min and 7 days) |
| `BACKEND_CORS_ORIGINS` | JSON list or comma-separated origins allowed to call the API |
| `GROQ_API_KEY`, `GROQ_MODEL_NAME` | Chat model. **Needed** for the chatbot |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` | Optional other providers an admin can switch to |
| `SMS_AI_PARSING` | `false` turns off AI reading of bank SMS (falls back to fixed patterns) |
| `MAILGUN_API_KEY`, `MAILGUN_URI`, `MAILGUN_FROM_ADDR` | Email sending. If any is empty the app only **logs** each email and its link |
| `EMAIL_FROM_NAME` | Sender display name |
| `EMAIL_WORKER_ENABLED` | `false` turns the background email worker off (tests do this) |
| `API_BASE_URL`, `FRONTEND_BASE_URL` | Public URLs in email links and the OAuth redirect. Default `http://localhost:8000` / `http://localhost:5173`. **Set both in production** |
| `OAUTH_ALLOWED_REDIRECT_HOSTS` | Hosts the Claude connector may redirect to (default `claude.ai,claude.com,localhost,127.0.0.1`) |
| `TYPESAFE_API_KEY` | Optional extra decision model; everything works without it |

Example `.env` for local development:

```env
DATABASE_URL=postgresql+asyncpg://smm:smm@localhost:5432/stalk_my_money
SECRET_KEY=change-me
GROQ_API_KEY=your-key
GROQ_MODEL_NAME=your-model
```

Never commit real keys.

### Run locally without Docker for the API

Only PostgreSQL runs in a container; the API runs from uv.

```bash
cd TraceMyMoneyAPI

uv sync                                              # 1. install dependencies (creates .venv)
docker compose -f docker-compose.dev.yml up -d       # 2. local PostgreSQL (smm / smm / stalk_my_money)
uv run alembic upgrade head                          # 3. create the tables
uv run uvicorn main:app --reload --port 8000         # 4. start the API with auto-reload
```

Stop the database later with `docker compose -f docker-compose.dev.yml down` (add `-v` only to delete the
data too). Already have PostgreSQL? Skip step 2 and point `DATABASE_URL` at it.

The web app's dev server expects the API on port **5000** unless `VITE_TM_BACKEND_URL` is set. Either start
uvicorn with `--port 5000`, or set `VITE_TM_BACKEND_URL=http://localhost:8000` in the UI (no trailing slash).

### Run with Docker

**A. Build and run the API image yourself.** The image serves on port 8000 and needs a reachable PostgreSQL
(start the dev database and run the migrations first, as above).

```bash
docker build -t smm-api .

# A container cannot reach your machine's "localhost", so use host.docker.internal
docker run --rm -p 8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -e DATABASE_URL=postgresql+asyncpg://smm:smm@host.docker.internal:5432/stalk_my_money \
  -e SECRET_KEY=change-me \
  -e GROQ_API_KEY=your-key -e GROQ_MODEL_NAME=your-model \
  smm-api
```

Migrations from the same image:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway \
  -e DATABASE_URL=postgresql+asyncpg://smm:smm@host.docker.internal:5432/stalk_my_money \
  smm-api uv run alembic upgrade head
```

**B. Production compose** (`docker-compose.yml`) runs the API (port 5000) and the MCP server (port 8090) on
the shared `edge-network`. See [Deployment](#deployment-and-configuration).

### Verify the setup ("hello world")

```bash
# 1. The API is up: should print 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs

# 2. Register (username 7 to 20 characters, password at least 8)
curl -s -X POST http://localhost:8000/register -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","username":"myusername","password":"password123"}'
```

New accounts must confirm their email before they can log in. With the Mailgun variables empty, the API
prints the email, including the confirmation link, in its log. Copy the `token` from that link and confirm:

```bash
curl -s -X POST http://localhost:8000/verify-email -H 'Content-Type: application/json' -d '{"token":"<token from the log>"}'

# 3. Log in: returns {"token": "...", "refresh_token": "...", "status_code": 200}
curl -s -X POST http://localhost:8000/login -H 'Content-Type: application/json' \
  -d '{"username":"myusername","password":"password123"}'

# 4. Call an authenticated endpoint
curl -s http://localhost:8000/banks/ -H "authorization: Bearer <token>"
```

---

## API documentation

### Base URL and versioning

- Production: `https://api.stalk-my-money.in`. Local: `http://localhost:8000`.
- There is no version prefix in the paths. The app version is the `VERSION` setting (default `1.0.0`).
- Interactive docs: `/docs` (Swagger UI). OpenAPI schema: `/openapi.json`. Import it into Postman or Insomnia.

### Authentication

1. `POST /login` with `{"username", "password"}` returns `{"token", "refresh_token", "status_code"}`.
   Login returns **403** (`"Email not verified ..."`) until the email is confirmed.
2. Send the token on every request: `authorization: Bearer <token>` (a raw token also works).
3. When the access token expires (30 minutes by default), `POST /refresh` with `{"refresh_token"}` returns a
   new pair. Refresh tokens last 7 days.
4. The SMS webhook uses its own ingest token (`X-Ingest-Token` header) created from the profile page.
5. The Claude connector uses OAuth 2.0 authorization code with PKCE (S256). Metadata is at
   `/.well-known/oauth-authorization-server`.

### Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/register` | Create an account and queue the confirmation email |
| POST | `/login`, `/refresh` | Get and renew tokens |
| POST | `/verify-email`, `/resend-verification` | Confirm email; resend the link |
| POST | `/forgot-password`, `/reset-password` | Request and complete a password reset |
| GET | `/banks/` | List accounts |
| POST / DELETE | `/banks/create`, `/banks/delete` | Create or delete an account |
| GET | `/expenses/` | List expenses (paginated, filterable) |
| POST | `/expenses/create`, `/expenses/create-bulk` | Add expenses |
| PATCH / DELETE | `/expenses/add-entry`, `/update-entry`, `/delete-entry`, `/delete` | Change entries or whole expenses |
| GET | `/expenses/graph-data`, `/expenses/analytics/overview` | Charts and analytics |
| GET / POST | `/entry-tags/`, `/entry-tags/create`, `/entry-tags/suggest` | Tags |
| GET / PATCH | `/user-preferences/`, `/user-preferences/update` | User preferences |
| POST | `/user/chat` | Chatbot (needs chatbot access) |
| GET / PATCH / POST | `/profile/`, `/profile/password` | Profile and password change |
| GET / POST / PATCH / DELETE | `/ingest/token`, `/ingest/settings`, `/ingest/pending` ... | SMS import setup and inbox |
| POST | `/ingest/sms` | SMS webhook (ingest token) |
| GET / PATCH / PUT | `/admin/...` | Admin: users, chatbot access, AI config, keys, flags, metrics |
| GET | `/feature-flags` | Public feature flags |
| GET / POST / DELETE | `/oauth/...`, `/.well-known/...` | Claude connector OAuth |

The full list with request and response schemas is always at `/docs`.

### Example: create an expense

```http
POST /expenses/create
authorization: Bearer <token>
Content-Type: application/json
```

The exact body is shown in `/docs` under `POST /expenses/create` (an `expenses` list of entries, the account
`bank_id`, and an optional `created_at` date).

### Example: list expenses

```http
GET /expenses/?bank_id=<bank uuid>&page_number=1&per_page=20
```

```json
{
  "expenses": [ ... ],
  "total_expenses": 42,
  "non_topup_total": 18240.5,
  "topup_total": 50000.0
}
```

### Errors

Errors use FastAPI's standard shape:

```json
{ "detail": "Email not verified. Check your inbox for the confirmation link." }
```

Validation errors (422) return `detail` as a list of `{loc, msg, type}` objects.

| Status | Meaning |
|---|---|
| 400 | The request is invalid (for example a duplicate account or bad data) |
| 401 | Missing, invalid or expired token |
| 403 | Not allowed (email not verified, chatbot not enabled, not an admin, account disabled) |
| 404 | Not found |
| 422 | Request body or query did not validate |
| 429 | Too many requests (see below) |
| 500 | Server error |

### Rate limits and pagination

- **Rate limits** apply to the email endpoints, per client IP per hour: `/verify-email` 20,
  `/resend-verification` 5, `/forgot-password` 5, `/reset-password` 10. Each account also has a 60 second
  cooldown between emails, and the chatbot can email at most 5 reports per hour per user. Other endpoints are
  not rate limited by the API.
- **Pagination:** `GET /expenses/` takes `page_number` (default 1) and `per_page` (default 5, maximum 10000).
  The response includes `total_expenses` so you can compute the page count.

---

## Deployment and configuration

### Build and deploy

`.github/workflows/deploy_on_ec2.yml`: every push builds a Docker image tagged `<branch>_<sha>`. A merge to
`master` tags it `latest` and deploys to the EC2 server with `docker compose up -d`. CI does **not** run the
tests yet, so run them locally first.

```bash
docker network create edge-network     # once per machine
docker compose up -d --build           # reads ../env/.env.prod (outside the repo)
```

### Environment-specific settings

| | Local | Production |
|---|---|---|
| Database | Dev container (`docker-compose.dev.yml`) | External PostgreSQL, `DATABASE_URL` in `../env/.env.prod` |
| Secrets | `.env` | `../env/.env.prod` on the server |
| Public URLs | localhost defaults | `API_BASE_URL` and `FRONTEND_BASE_URL` set in `docker-compose.yml` |
| Email | Console only (logged) | Mailgun variables set |
| uvicorn | `--reload` | No `--reload` |

### Infrastructure notes

- One small EC2 instance (about 1 GB RAM) runs the API container, the MCP container, the nginx gateway
  (`gateway-nginx` repo) and other projects. Disk and memory are tight: run `docker builder prune -af`
  now and then, and never `docker compose down -v` (it can delete data volumes).
- nginx terminates TLS for `api.stalk-my-money.in` and forwards to the API on port 5000. `/mcp` goes to the
  MCP server on port 8090 with buffering off.
- If the API stops answering, nginx returns a 504 and the browser shows it as a CORS error. Check
  `docker logs stalkmymoney_api`, `docker stats`, `free -m` and `df -h /`.

### Migrations and seed data

```bash
uv run alembic upgrade head                        # apply all migrations
uv run alembic current                             # which revision is applied
uv run alembic revision -m "describe the change"   # new migration file
uv run alembic downgrade -1                        # undo the last one
```

- **The deploy does not run migrations.** After deploying code with a new migration, run it by hand:
  `docker exec stalkmymoney_api uv run alembic upgrade head`. Deploying code before its migration breaks the API
  with "relation/column does not exist".
- New tables must also `REVOKE` access from the read-only role `smm_chat_readonly` (see existing migrations).
- There is no seed data. Accounts and expenses are created through the API.
- `scripts/migrate_mongo_to_pg.py` is the one-time MongoDB to PostgreSQL import tool (needs `MONGODB_URL`).

### MCP server

A small stateless HTTP server in `mcp_server/`. Run it locally (needs the API running):

```bash
uv sync --extra mcp
SMM_API_BASE_URL=http://localhost:8000 SMM_MCP_TRANSPORT=http uv run --extra mcp python -m mcp_server.server
```

It listens on port 8090 at `/mcp`. `fastmcp` is pinned to exactly `3.4.0`: after changing the pin, run
`uv lock` and commit `uv.lock` (the images install with `--frozen`). Details: [`mcp_server/README.md`](mcp_server/README.md).

---

## Development workflow

### Running tests

Tests use a separate database, `stalk_my_money_test`, on the same local PostgreSQL.

```bash
docker compose -f docker-compose.dev.yml up -d
docker exec smm_postgres_dev createdb -U smm stalk_my_money_test      # once
DATABASE_URL=postgresql+asyncpg://smm:smm@localhost:5432/stalk_my_money_test uv run alembic upgrade head

uv run pytest                                               # everything
uv run pytest tests/characterization/test_expenses.py -v    # one file
```

### Linting and formatting

[ruff](https://docs.astral.sh/ruff/) does both. Settings are in `pyproject.toml`: line length 120, double
quotes, rules `E`, `F`, `I` (imports) and `UP`.

```bash
uv run ruff check --fix .
uv run ruff format .
uv run pre-commit install        # run ruff automatically on every commit
```

### Branching and commits

- `master` is the production branch: merging to it deploys. Work on a feature branch and open a pull request.
- Commit messages start with the area: `[BACKEND] - Short description of the change` (the UI repo uses
  `[FRONTEND] - ...`).
- Before merging: run `uv run pytest` and `uv run ruff check .`. For a change that adds a migration, run it on
  the server right after the deploy.
