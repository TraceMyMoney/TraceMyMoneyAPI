# SPEC: Daily expense limit (red warning when a day goes over)

Status: SPEC written, waiting for the user's OK on the "Open questions" (section 5). No code yet.
Lives in the API repo because it needs a migration, a schema change and a new query (more backend than UI work). UI steps are listed in section 3 and in `PLAN.md`.

## 1. What

A user can set a **daily expense limit** (example: Rs 150) in their preferences. When the total spent on one
calendar day is **more than** the limit, that day's expense rows are shown in **red** with a "Limit crossed" hint,
so the user sees at once that they overspent that day.

Example: limit = 150. Monday: Food 100 (HDFC) + Auto 60 (Cash) = 160 -> Monday is red.
Tuesday: 150 exactly -> not red (only strictly more than the limit counts). No limit set -> nothing is ever red.

## 2. Rules

### Data and API (backend)
- New nullable column `user_preferences.daily_expense_limit NUMERIC(18,2)`. `NULL` = no limit (the default, so
  every existing user is unchanged). Alembic migration, run by hand on production
  (`docker exec stalkmymoney_api uv run alembic upgrade head`). The column is on an existing table, so no new
  `REVOKE` is needed; confirm in the migration review.
- `GET /user-preferences/` returns `daily_expense_limit` (number or `null`).
  `PATCH /user-preferences/update` accepts it. Value must be greater than 0 and at most 10,000,000, with up to
  2 decimals; `null` clears the limit. Anything else is a 422 with a clear message, never a 500.
  Because `update_preferences` uses `exclude_unset`, an explicit `null` here must CLEAR the limit (the current
  code ignores `null` for the two array fields; this field needs the opposite rule, called out in the plan).
- **Day total** = sum of all debit entries (positive amounts) of that user for that calendar day, **across all
  banks/accounts**. Credits/top-ups (negative amounts) do not reduce it (see open question Q1).
- The expense list endpoint (`GET`/search used by the table) adds one field per expense row: `day_total`
  (the whole-day total across all banks for the day of that row). It is computed in ONE grouped query for the
  days on the returned page, not per row, and it must be correct even when the day's other bank rows are on
  another page.
- The API returns the numbers (`day_total`, and the limit via preferences). The UI does the comparison, so the red
  state updates the moment the user edits the limit, without reloading the list.
- Every query filters by `user_id`.
- The calendar day is decided the same way as the existing analytics daily totals (`func.date(created_at)`), so the
  two screens never disagree (see open question Q3 about time zone).

### UI (frontend)
- A "Daily expense limit (Rs)" field in the same place the user already sets preferences (privacy mode, page size).
  Empty = no limit. Save through the store (`updateUserPreferences`), never Axios in the component.
  Validation message shown inline for 0, negative, or non-number.
- `limitCrossed = limit != null && day_total > limit`. When true, every expense row of that day is shown in red
  (`--red` #FF3B5C) with a small "Limit crossed" label and "Rs day_total / Rs limit" in the expanded row.
  Do not use colour alone: the label and an icon carry the meaning too (colour-blind users).
- Works in both the desktop table and the phone view. Phone view gets its own red styling; tablet and desktop
  layouts are not changed except for the new red state.
- Privacy mode on: the row is still red, but amounts stay hidden (`••••`); the "Rs day_total / Rs limit" text is
  hidden too.
- Light and dark mode both checked. Red uses the existing CSS variable, no new colour.
- **Design draft (an Artifact) must be approved before any UI code** (project rule).

## 3. Work split

| Where | What |
|---|---|
| API | migration, table column, schema, preference service (null clears), `day_total` in expense list, tests |
| UI | store field + save, preference input, red row (desktop + phone), design draft first |
| Docs | update `TraceMyMoneyAPI/CLAUDE.md` / root `CLAUDE.md` if anything about the project changes |

Branches (same title in both repos): `BACKEND-FEATURE-daily-expense-limit`, `FRONTEND-FEATURE-daily-expense-limit`.

## 4. Out of scope (for now)
- Weekly or monthly limits, a different limit per weekday or per bank/account.
- Push, email or toast alerts when the limit is crossed (colour only).
- Blocking or warning at the moment of adding an expense (the red appears in the list afterwards).
- Chatbot and MCP support (setting the limit by chat, "did I cross my limit today?"). Easy follow-up on the same service.
- Marking single entries red inside a day (the whole day's rows are marked).
- Back-filling or storing history of past limits: the CURRENT limit is applied to all days, old ones too (Q2).

## 5. Open questions (my defaults are in bold; tell me if you want a different one)
- **Q1. Do credits/top-ups reduce the day total?** Default: **No**, only debits count (a top-up is not "undoing" spending).
- **Q2. When the limit changes, do old days change colour?** Default: **Yes**, the current limit applies to every day
  (simple, nothing stored per day). The other option needs a limit history table.
- **Q3. Which time zone decides "the day"?** Default: **same as analytics (`func.date(created_at)`)**. If the server
  runs in UTC, an entry added at 1 AM India time can land on the previous day. This is my guess; I will check
  how the existing rows' `day` / `created_at` behave before building and report.
- **Q4. Do tags in "default excluded tags" count toward the day total?** Default: **Yes, they count** (the limit is about
  real spending). Downside: the day's total in the red hint may differ from a table total that hides excluded tags.
- **Q5. Which rows turn red?** Default: **all expense rows of that day (every bank)**, because the limit is about the
  day, not one account.

## 6. Done means
1. `uv run pytest` and `uv run ruff check .` pass (state any old known failure).
2. Tests prove: preference save and read (value, `null` clears, 0 / negative / text / too large -> 422, other user's
   data untouched); `day_total` sums across banks, ignores credits (per Q1), is right when a day's rows are split
   over pages, and is per user; no limit -> UI never red.
3. Migration upgrades and downgrades cleanly on the dev Postgres (`smm_postgres_dev`); existing users keep `NULL`.
4. A real check in the running app: set 150, add 100 + 60 on two banks the same day -> both rows red; edit one entry
   to bring it to 150 -> not red; clear the limit -> not red; privacy mode hides amounts; phone view checked.
5. `PLAN.md` status updated, problems logged, and the commit message lines given (`[BACKEND] - ...`, `[FRONTEND] - ...`).
