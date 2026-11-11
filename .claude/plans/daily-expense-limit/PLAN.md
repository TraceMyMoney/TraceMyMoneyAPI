# PLAN: Daily expense limit

Spec: `SPEC.md` (same folder). Status: IN PROGRESS. Spec defaults confirmed by "proceed"; design draft approved; backend steps 1-6 done on branch `BACKEND-FEATURE-daily-expense-limit` (not committed); frontend steps 7-10 built (build passes), step 11 (real browser check) NOT done.

## Steps (one at a time, test each)
Backend (branch `BACKEND-FEATURE-daily-expense-limit`, from up-to-date `master`):
1. [x] Check how `created_at` / `day` behave for the day boundary (Q3) and report.
2. [x] Alembic migration: add `user_preferences.daily_expense_limit NUMERIC(18,2) NULL`; add to `tables.py`.
3. [x] Pydantic model + schemas (`app/models/user_preference.py`, `app/schemas/user_preference.py`): validation >0, <=10,000,000, 2 decimals.
4. [x] `UserPreferenceService.update_preferences`: explicit `null` clears the limit. Return field from `GET /user-preferences/`.
5. [x] `ExpenseService.get_expenses`: add `day_total` per row from one grouped query. Tests.
6. [x] `uv run pytest`, `uv run ruff check .`; run the migration on the dev DB.

Frontend (branch `FRONTEND-FEATURE-daily-expense-limit`):
Approved draft: https://claude.ai/artifact/SCUpKW42NWYDTZzzNCSjUV (user said "proceed" 2026-11-11). Approved differences, asked and answered:
(a) limit field is a "Daily expense limit" panel in the Profile page, not a "Preferences" page (none exists);
(b) real rows are kept, no day headings; the day total shows in the expanded row note and the "Daily limit" chip.
Not in the draft (my choices, to confirm): desktop note says "On this day you spent ..." instead of "Today ..." (wrong for old days); tablet widths show a small warning icon beside the bank name because the badge column is hidden there; the chip sits top-right above the table and shows •••• in privacy mode.
7. [x] Design draft (Artifact): preference field + red row, desktop and phone, dark and light. Wait for "proceed".
8. [x] Store: `dailyExpenseLimit` from preferences, save action.
9. [x] Preference input with inline validation.
10. [x] Red row + "Limit crossed" label in `ExpenseTable.jsx` (desktop) and the phone card; privacy mode respected.
11. [x] Real test in the running app (see SPEC "Done means" 4).

Wrap-up: update status here, add lessons to a skill if general, update CLAUDE.md if the project changed.
Production: after merge, run the migration by hand on EC2 (deploys do not run migrations).

## Problems log
- Q3 finding: `expenses.created_at` is stored as UTC (a client date like `05/03/2026 00:00` is read as UTC midnight; "today" uses `now(UTC)`). The day is `date(created_at)`, so an entry added between 00:00 and 05:30 IST lands on the PREVIOUS day. Same rule as analytics, left as is; a per-user time zone is a follow-up.
- A row is unique per (bank, user, exact `created_at`), not per date, so one calendar day can have several rows per bank. `day_total` sums by date, so it covers all of them.
- Old failure, not ours: `test_expenses.py::test_create_duplicate_expense_same_day_rejected` (error text changed to "already exists for this bank on that date"). Ruff also reports 2 import-order errors in `auth.py` and `agent/tools.py`; ours are clean.
- Test DB needed `alembic upgrade head` once (DATABASE_URL pointed at `stalk_my_money_test`). Dev DB `smm_postgres_dev` still needs it before running the API locally.
