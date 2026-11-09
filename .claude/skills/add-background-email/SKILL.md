---
name: add-background-email
description: Add transactional email (signup confirmation, password reset, emailed reports) to a FastAPI + Postgres app so the user never waits for the send. Uses a Postgres outbox table, an in-process worker and Mailgun's HTTP API. Use when asked to "send emails", "email verification", "forgot password" or "email me a report".
---

# Add background email to a FastAPI app

Reference implementation: `TraceMyMoneyAPI/app/services/email/` (sender, templates,
outbox, jobs, worker, tokens) and `app/services/account_email_service.py`.
Plan it came from: `.claude/plans/send-email/PLAN.md` (in this repo) (its Problems log has the history).

## 1. Core rule: handlers only INSERT

A request handler never calls the mail provider. It writes a row to an `email_jobs`
table (milliseconds) and returns. A worker sends later.
- Why Postgres and not Redis/Celery: already there, survives restarts, one less service.
- Worker lives in the API `lifespan` (start task on boot, cancel on shutdown), behind an
  `EMAIL_WORKER_ENABLED` flag so tests can turn it off.
- Claim rows with `FOR UPDATE SKIP LOCKED`. Claiming sets `run_after = now() + 5 min` as a
  lease, so a crash mid-send gets retried instead of lost.
- Statuses: pending / sending / sent / failed. Retry delays 1m, 5m, 30m, 2h; max 5 attempts.
- Provider 5xx, 429, network errors = retry. Other 4xx = permanent, fail at once.
- Wake the worker with an `asyncio.Event` after insert so sends are instant, not polled.
- Scrub the payload when a job becomes sent/failed (it may hold a raw token).

## 2. Tokens (verify / reset)

- Generate with `secrets.token_urlsafe`, store only the sha256 hash, single use.
- TTL: verify 24h, reset 1h. A new request retires older unused tokens.
- Consume atomically: `UPDATE ... WHERE used_at IS NULL AND expires_at > now() RETURNING`.
- Password reset also proves the email, so it may verify the account.

## 3. Anti-abuse and anti-enumeration

- forgot-password and resend-verification ALWAYS return the same 200 message, whether
  or not the email exists.
- Per-account cooldown (60s, in DB) plus per-IP in-memory rate limit.
- Block login until verified (403 with a clear "Email not verified" message).
  **Grandfather existing users in the migration** (`email_verified_at = now()`) or you lock
  everyone out on deploy.

## 4. Mailgun (HTTP API, no SDK)

- `httpx` POST, basic auth `("api", key)`, form data, attachments as multipart `attachment`.
- Env vars: `MAILGUN_API_KEY`, `MAILGUN_URI` (full `.../v3/<domain>/messages` URL),
  `MAILGUN_FROM_ADDR`.
- If any is empty, use a **console backend** that logs the email and link. Local dev and
  tests then need no keys.
- The sending domain must be Active in Mailgun, or every send is refused.

## 5. Emailing reports from a chatbot/agent

- Separate tools: `export_expenses` (download, never emails) and `email_expenses`
  (needs an explicit `user_asked_for_email=true`). Ambiguous request: ask "download or email?".
- No recipient argument. Only ever the account's own email (mask it in the reply).
- Cap per hour. Validate and check for empty data in chat, before queueing.
- Store filters in the job, build the file at send time. Share one helper between the
  download path and the email path.

## 6. Database traps

- If a restricted DB role exists (e.g. the text-to-SQL chat role), `REVOKE` it on the new
  tables in the same migration. Default privileges give it SELECT on new tables.
- Migration order: add column, grandfather UPDATE, create tables, indexes, revoke.

## 7. Frontend traps

- Backend base-URL env vars must NOT end with `/` (got `POST //register`).
- No-router SPA: "back to login" must set the in-memory view, not only the URL.
- React StrictMode runs effects twice in dev: guard the verify-token call with a `useRef`,
  or the single-use token is spent by the first call and the second shows an error.
- Match the 403 by its prefix ("Email not verified") to show the resend banner.
- Public `FRONTEND_BASE_URL` must be set in the deployed container, or links say localhost.

## 8. Testing

- Use `example.com` addresses; pydantic `EmailStr` rejects the `.test` TLD.
- When adding a login gate, fix the shared test fixture once (mark user verified).
- Count queued jobs by `kind`, since fixtures may queue some too.
- Test: single-use, expiry, retry/permanent-failure paths, same response for unknown email.

## 9. Deploy checklist

1. Mailgun vars into the prod env file; domain Active.
2. Run the Alembic migration (production DB too). Backend first, then frontend.
3. Real checks: signup mail, reset mail (second click must fail), chatbot "email me" arrives
   with the PDF, chatbot "download" sends nothing, an old account still logs in.
4. On failure: `select kind,status,attempts,last_error from email_jobs order by created_at desc limit 5`.

## 10. Known limit

After a password reset, already-issued JWTs stay valid until they expire (no revocation
list). Mention it to the user; fix only if asked.
