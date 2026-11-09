# PLAN: Email feature (verify signup, reset password, email expense PDF)

Status: DONE. Steps 1-8 complete; 122 backend tests pass (+1 old known failure); verified by the user with real Mailgun sends (signup, reset, chatbot PDF, download-without-email). Decisions taken by default: Postgres outbox + worker, block login until verified (existing users grandfathered).

## 1. Goal

1. **Signup confirmation:** a new user gets an email with a link and must click it to activate the account.
2. **Password reset:** "Forgot password" sends an email with a one-time link to set a new password.
3. **Chatbot "email me my expenses":** the user asks the chatbot for a date range, and a PDF of those expenses arrives in their inbox.
4. **Never make the user wait for an email.** Every email is sent in the background. The API replies immediately.

## 2. What exists today (checked in the code)

- `users` table has `email` (unique) and `is_subscribed_to_emails`, but **no verified flag** and nothing sends email.
- `POST /register` creates the user and returns success. `POST /login` checks username and password only.
- The chatbot has an `export_expenses` tool (`app/services/agent/tools.py`) that builds a PDF/CSV via `app/services/agent/export.py` (reportlab) and returns it to the browser as base64. Only the delivery is missing.
- `config.py` has unused Celery/Redis settings, but **celery and redis are not installed** and there is no Redis on EC2.
- Frontend routes by `window.location.pathname` in `App.jsx` (no router). The OAuth approval page already works this way, so new pages can copy it.
- Deploy: one API container on EC2, env from `../env/.env.prod`, migrations via `alembic upgrade head`.

## 3. Design

### 3.1 Background sending (the important part)

An **email outbox in Postgres plus a small worker inside the API process.**

- New table `email_jobs`: `id, user_id, kind, payload (JSON), status (pending/sending/sent/failed), attempts, run_after, last_error, created_at, sent_at`.
- A request handler only **inserts a row** (a few ms) and returns. It never talks to the mail server.
- A worker loop starts in the FastAPI lifespan. It claims due rows with `FOR UPDATE SKIP LOCKED`, sends, and marks them `sent`. On failure it retries with growing delay (1m, 5m, 30m) and gives up after 5 attempts (`failed`, error kept).
- Why this and not the alternatives:
  - **FastAPI `BackgroundTasks`:** simplest, but a deploy or crash between "request done" and "email sent" loses the email silently, and there are no retries.
  - **Celery + Redis:** the "proper" tool, but it adds Redis and a second container on a small EC2 box for three kinds of email.
  - **Outbox:** survives restarts, retries, needs no new infrastructure, and is easy to test. If volume ever grows, the worker can move to its own container without changing the handlers.
- PDF jobs store the **filters** (date range, bank, tag), not the PDF bytes. The worker builds the PDF at send time, so the DB stays small and the chat reply stays instant.

### 3.2 Sending itself (Mailgun HTTP API, same as obsidian-clone)

**How obsidian-clone does it** (`MDStackBackend/app/modules/users/email.py`):
- Plain `httpx.AsyncClient(timeout=10)` POST to `MAILGUN_URI` with `auth=("api", MAILGUN_API_KEY)` and form `data={from, to, subject, html, text}`, then `raise_for_status()`.
- Sender shown as `"MarkdownStack <addr>"`, built from `MAILGUN_FROM_ADDR`.
- Best-effort: returns True/False, never raises. If any of the three settings is empty it logs a warning and skips (so local dev with no key just doesn't send).
- Links are `FRONTEND_BASE_URL + /verify-email?token=...` and `/reset-password?token=...`; 24h verify, 1h reset; token = `secrets.token_urlsafe(32)`.
- **Gap we are fixing:** obsidian's register/forgot handlers `await` the Mailgun call inline, so a slow Mailgun makes the user wait (up to the 10 s timeout). Only its follow-notifications are fire-and-forget. We keep its client code but put it behind the outbox worker (3.1), so no request ever waits on Mailgun.

**What we reuse / change:**
- Same client shape: one `mailgun_send(to, subject, html, text, attachments=None)` function using `httpx` + basic auth `("api", key)`.
- Mailgun accepts attachments in the same call (multipart `attachment` file field), so the PDF email uses the same function with `files=`.
- A `console` backend (log the email and link, no network) stays for local dev and tests. Selected automatically when the Mailgun vars are empty, like obsidian's skip, but it logs the link so we can click it in dev.
- `httpx` moves into the **base dependencies** (today it is only in the dev group and the `mcp` extra, and the prod image would otherwise not have it).
- The worker, not the sender, decides retries. The sender just raises on failure so the worker can retry (obsidian swallows errors, which is fine for fire-and-forget but would make retries impossible).
- Templates: HTML plus plain-text versions in `app/templates/email/`, styled like the app (dark, acid green) instead of obsidian's gold.

**Your Mailgun values (names only, never commit the key):**
- `MAILGUN_API_KEY`: goes only in `../env/.env.prod` on EC2 and your local `.env`.
- `MAILGUN_URI=https://api.mailgun.net/v3/app.stalk-my-money.in/messages` (US region endpoint, sending domain `app.stalk-my-money.in`).
- `MAILGUN_FROM_ADDR=parimal@app.stalk-my-money.in`, shown as `Stalk My Money <parimal@app.stalk-my-money.in>`.
- Since the sending domain is already set up in Mailgun, the DNS question from the first draft is mostly answered. Still verify in the Mailgun dashboard that the domain shows as "Active" (SPF and DKIM green) before the real send test.

### 3.3 Signup confirmation

- New `users.email_verified_at` (nullable timestamp).
- New table `email_tokens`: `id, user_id, purpose (verify/reset), token_hash, expires_at, used_at`. Tokens are random, stored **sha256-hashed** (same approach as the OAuth tokens), single use.
- `POST /register` creates the user, inserts a verify token and an `email_jobs` row, and returns at once.
- `POST /verify-email` (token) marks the user verified.
- `POST /resend-verification` (email) always answers 200 (no hint whether the email exists), rate-limited.
- `POST /login` rejects an unverified user with a clear 403 message ("Please confirm your email") that the UI can act on.
- **Existing users are grandfathered:** the migration sets `email_verified_at = now()` for everyone already in the table, so nobody gets locked out.
- Verify link expiry: 24 hours.

### 3.4 Password reset

- `POST /forgot-password` (email): always answers 200 with the same message whether or not the account exists. If it exists, it queues the email. Rate-limited per email and per IP.
- Reset link expiry: 1 hour, single use. Requesting a new link invalidates older ones.
- `POST /reset-password` (token, new password): validates the token, sets the password (Argon2, same as register), marks the token used.
- After a reset, existing refresh tokens should stop working (check how refresh is validated; if it can't be revoked today, note it and keep it out of scope).

### 3.5 Chatbot: "email me the PDF"

- Add an `email_expenses` tool next to `export_expenses`, with the same filters (date range, bank, tag, keyword, top_n).
- Pull the shared "find rows" logic out of `export_expenses` into one helper so both tools use identical filtering (no copy-paste drift).
- **Only sends to the logged-in user's own address.** The tool takes no recipient argument, so it can't be used to mail other people.
- The tool queues a `pdf_report` job and returns "I've queued it, it should reach you at j***@gmail.com in a minute". The chat reply is instant.
- If the date range matches nothing, say so and don't send an empty PDF.
- Cap the report size (same 100-group limit as export) so attachments stay small.
- **Email only on an explicit request. Download stays the default.**
  - "download / export / give me / show me a PDF or CSV" -> `export_expenses` (file in chat, **no email, ever**).
  - "email / mail / send to my inbox" -> `email_expenses`.
  - Ambiguous ("send me my expenses", "share the report") -> the chatbot asks one short question ("Download here, or email it to you?") and does nothing until you answer.
  - The `email_expenses` tool description says: "Use ONLY when the user explicitly asks for email. Never use for download/export." The system prompt repeats this, and `export_expenses` says "this never sends email".
  - Safety net: before queuing, `email_expenses` requires the model to pass `user_asked_for_email=true`, and the reply always states where it went ("Queued to j***@gmail.com"), so a wrong trigger is visible immediately.
  - Nothing else in the app ever sends a report on its own (no schedules, no auto-emails after export).
- Add the tool to the right tool category list in `agent_service.py` so the chatbot picks it, and add a line to the system prompt.

### 3.6 Frontend (`TraceMyMoneyUI`)

- Register: after signup show "Check your email to confirm your account" with a Resend button.
- `/verify-email?token=...` page: confirms, then shows "Verified, you can log in".
- Login: "Forgot password?" link, and a friendly message plus Resend when the account is unverified.
- `/forgot-password` page (enter email) and `/reset-password?token=...` page (new password, confirm).
- All via store actions in `useStore.js`, same pattern as the OAuth page. Tablet and desktop layouts stay untouched.

### 3.7 Config (new env vars, none are secrets except the password)

`MAILGUN_API_KEY` (the only secret), `MAILGUN_URI`, `MAILGUN_FROM_ADDR`, optional `EMAIL_FROM_NAME` (default "Stalk My Money"). Same names as obsidian-clone so the two projects read alike. If any Mailgun var is empty the app uses the console backend. Link base reuses the existing `FRONTEND_BASE_URL`, which `docker-compose.yml` already sets to `https://app.stalk-my-money.in`.

## 4. Build order (each step small, testable, one commit)

- [x] **Step 1: Foundations.** `email_jobs`, `email_tokens`, `users.email_verified_at` (grandfather existing users), Alembic migration, config vars.
- [x] **Step 2: Sender + templates.** Mailgun client modelled on obsidian-clone (httpx, basic auth, optional attachment), console fallback, HTML/text templates, `httpx` into base deps plus `uv lock`. Tests mock the HTTP call (no real Mailgun in tests).
- [x] **Step 3: Outbox worker.** Enqueue helper, claim/send/retry loop in the lifespan, tests (success, failure then retry, gives up after N, two workers don't double-send).
- [x] **Step 4: Signup confirmation.** Register queues the email, verify and resend endpoints, login blocks unverified. Tests.
- [x] **Step 5: Password reset.** Forgot and reset endpoints, rate limiting, tests (expired, reused, unknown email gives the same answer).
- [x] **Step 6: Frontend.** Register message, verify page, forgot/reset pages, login changes. Build and screenshot check.
- [x] **Step 7: Chatbot PDF email.** Shared row helper, `email_expenses` tool, prompt and category wiring, tests.
- [x] **Step 8: Deploy prep.** Add the three Mailgun vars to `../env/.env.prod` on EC2, check the domain is Active in Mailgun, README note, smoke test on production (one real verify email and one real PDF to your own inbox).

## 5. How we know it works (checks per step)

- Full test suite stays green (today: 80 pass, 1 known old failure `test_create_duplicate_expense_same_day_rejected`).
- Register/forgot/email-PDF endpoints return in well under a second **even when the mail server is made to hang** (test with a sender that sleeps 30 s).
- A job that fails once is retried and eventually sent; a permanently failing job ends as `failed` with the error saved.
- Restarting the API with jobs still pending does not lose them.
- Chatbot routing tests: "download my April expenses" creates **zero** `email_jobs` rows; "email me my April expenses" creates exactly one; an ambiguous "send me my April expenses" creates none and asks which one.
- Console backend: a real end-to-end run locally (register, read the link from the log, verify, log in; forgot, reset, log in).
- A real send to your own inbox before calling it done.

## 6. Security checklist

- Tokens random (32 bytes), stored hashed, expiring, single use.
- `forgot-password` and `resend-verification` never reveal whether an email exists.
- Rate limits on every endpoint that triggers an email (otherwise it's a spam cannon).
- Emails only go to the account owner's address. Chatbot tool has no recipient parameter.
- Reset and verify links contain only the opaque token, never user ids or passwords.
- No secrets in the repo: SMTP password lives in `.env.prod` on EC2 only.
- Log job ids and statuses, never token values or full email bodies.

## 7. Open decisions (my recommendation first)

1. **Background mechanism:** Postgres outbox + in-process worker (recommended) / simple `BackgroundTasks` / Celery + Redis. *(Still open. Obsidian's `asyncio.create_task` fire-and-forget is the lightest option, but it loses emails on restart and cannot retry.)*
2. ~~Email provider~~ **Decided: Mailgun HTTP API**, same as obsidian-clone.
3. **Block login until verified?** Yes for new users, existing users grandfathered (recommended) / allow login but show a banner. *(Still open.)*
4. ~~Sender address / DNS~~ **Decided:** `parimal@app.stalk-my-money.in` on the `app.stalk-my-money.in` Mailgun domain. Only a dashboard check remains (domain Active).
5. **MCP/Claude connector:** also give the MCP server an `email_expenses` tool? (Recommended later, not in this plan.)
6. **Mailgun key hygiene:** the key was pasted into chat as a placeholder, so nothing real is in this plan. Put the real key only in `.env.prod`/`.env`; if you ever pasted a real one anywhere shared, rotate it in Mailgun.

## 8. Out of scope (for now)

- Marketing or digest emails, and `is_subscribed_to_emails` unsubscribe flow (that flag only matters for non-transactional mail).
- Changing the email address, 2FA, magic-link login.
- A queue dashboard in the admin page.
- Moving the worker to its own container (easy later if needed).

## 9. After the feature

- Ask: did we learn something reusable? Likely candidate for a skill: **"add background email to a FastAPI app"** (outbox table, worker, token hashing, no-enumeration rules).
- Commit messages, one per step, in `[BACKEND] - ...` / `[FRONTEND] - ...` format.

## 10. Problems log

Add an entry the moment something breaks, so nothing is forgotten. At the end, keep only the GENERAL ones for the skill; leave the one-offs here.

Format:
- **What happened:** the error text
- **Cause:** the real reason (once known)
- **Fix:** what we changed
- **General or one-off?** (general = would bite another project too)

- **What happened:** local Postgres was down (`Connection refused 127.0.0.1:5432`) when running the migration.
  **Cause:** Docker Desktop wasn't running in WSL. **Fix:** user started Docker, `docker compose -f docker-compose.dev.yml up -d`. **General or one-off?** one-off.
- **What happened:** my shell command hung for 2 minutes.
  **Cause:** a stray `cat > file` with no heredoc waits for stdin forever. **Fix:** stopped the task. **General?** one-off (my typo).
- **What happened:** register returned 422 in the new tests. **Cause:** `email-validator` (pydantic `EmailStr`) rejects the reserved `.test` TLD. **Fix:** use `example.com` addresses in tests. **General?** yes, small: don't use `.test` emails with `EmailStr`.
- **What happened:** existing tests that register then log in broke. **Cause:** login now needs a verified email. **Fix:** the `registered_user` fixture (and one ingest test) mark the user verified. **General?** yes: when adding a gate to login, fix shared test fixtures once.
- **What happened:** frontend dev run got `Not Found`; API log showed `POST //register`. **Cause:** I set `VITE_TM_BACKEND_URL` with a trailing slash and the store builds `${BASE_URL}/register`. **Fix:** no slash (prod's value has none). **General?** yes: backend base URL env vars must not end with `/`.
- **What happened:** after "Verified / Password updated", the Sign In button showed the landing page, not the login form. **Cause:** no router; `/` for a logged-out visitor defaults to landing. **Fix:** `useGoLogin()` pushes `/` and switches the in-memory view to login. **General?** yes (no-router SPAs): navigating "back to login" must set the view state, not just the URL.
- **What happened:** new tests counted one extra email job. **Cause:** the shared `registered_user` fixture now queues a verify email. **Fix:** count by job kind. **General?** one-off.
- **Design note (not an error):** a pending verify/reset job holds the raw token in `payload` until sent; the worker scrubs it on `sent` and `failed`. The chat DB role has no access to `email_jobs`/`email_tokens` (revoked in the migration, because new tables otherwise get SELECT by default).
- **Known limit:** after a password reset, already-issued JWTs (30 min access, 7 day refresh) stay valid; there is no revocation list today. Out of scope here.
