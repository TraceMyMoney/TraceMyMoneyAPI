# PLAN: Tags CRUD

Status: IN PROGRESS. SPEC.md written; Step 1 done (on `master`, uncommitted, see Step 0). Waiting on the user: how to handle the uncommitted changes so Step 0 (branches) can happen, then "proceed". UI work additionally waits for an approved, refreshed design draft (Step 4b). Step order: 0 branches, 1, 2, 2b, 3, 4, 4b draft gate, 5, 6, 7, 8.
Spec: `.claude/plans/tags-crud/SPEC.md`. One step at a time, one commit message per step, log problems at the bottom.

## Build order

- [ ] **Step 0: Branches (before ANY further code).** Rule: root/API/UI `CLAUDE.md` "Branches". Both repos are separate git repos. For each: check `git status` first; **if there are uncommitted changes, STOP and ask the user, never switch silently.** Then, from an up-to-date master:
  - `cd TraceMyMoneyAPI && git fetch origin && git switch -c BACKEND-FEATURE-tags-crud origin/master`
  - `cd TraceMyMoneyUI && git fetch origin && git switch -c FRONTEND-FEATURE-tags-crud origin/master`
  - Creating branches is expected; commits and pushes stay with the user.
  - **Blockers found on 2026-11-09 (read-only `git status`, nothing switched):** API is on `master` with uncommitted changes: the user's `CLAUDE.md` edit PLUS my Step 1 work (`app/models/expense_entry_tag.py`, `app/schemas/entry_tag.py`, `app/services/entry_tag_service.py`, `app/services/agent/tools.py`, `tests/characterization/test_entry_tags.py`, `tests/characterization/test_user_preferences.py`). UI is on `master` with the user's uncommitted `CLAUDE.md` edit only. Step 1 was written before the Branches rule existed. The user must say how to carry these (for example: commit the `CLAUDE.md` edits on master first, and for the API `git switch -c` from the current commit or `git stash` then re-apply, so Step 1 lands on the feature branch). Do nothing until they answer.

- [x] **Step 1: Service layer. DONE** (tests: 24 pass in tag + preference files; full suite 138 pass, 1 old known failure `test_create_duplicate_expense_same_day_rejected`). Delivered: `normalize_tag_name` in `app/schemas/entry_tag.py` (schema applies it, service re-applies), `EntryTagUpdate` now requires `name`, `get_tags`/`get_tag_by_id`/new `get_tag_by_name` return `entry_count` (one grouped query), `update_tag` checks duplicates (ValueError), `delete_tag` is one transaction and returns the untagged count (None = not found; **was bool**), case-insensitive duplicate check on create. Two small compatibility fixes in `agent/tools.py` so the old chatbot tools keep working (catch the rename ValueError; `delete_tag` result checked with `is not None`, since 0 is a valid count). Old test `test_default_excluded_tags_round_trip` now expects "Emi" (the new rule). Plan details below:
  - `get_tags` returns `entry_count` (one grouped LEFT JOIN on `expense_entry_tag_links`), sorted by lower(name).
  - `update_tag`: trim, case-insensitive duplicate check excluding the tag itself, raise `ValueError` on clash.
  - `delete_tag`: one transaction: delete tag + remove id from `user_preferences.default_excluded_tags`; return the number of entries that lost it (or None if not found).
  - Helper to find a tag by name (case-insensitive) for MCP/chatbot to share.
  - Shared `normalize_tag_name()` (trim, collapse spaces, upper-case first letter only) used by create and rename; create's duplicate check becomes case-insensitive. Tests: "food" -> "Food", "EMI" stays, "  rent   and bills " -> "Rent and bills", "food" vs "Food" clash.
  - Schema: `EntryTagUpdate` with 1-50 length and trim. Check `app/models/expense_entry_tag.py` for `entry_count`.
  - Tests in `tests/characterization/test_entry_tags.py` (service level): duplicate, case-only rename, cleanup of excluded tags, other user's tag.

- [ ] **Step 2: REST endpoints.** `PATCH /entry-tags/{tag_id}`, `DELETE /entry-tags/{tag_id}`; `GET /entry-tags/` adds `entry_count`. Thin handlers, 400 on clash, 404 on missing/other user's tag, invalid UUID -> 404. Tests in `tests/characterization/test_entry_tags.py` (API level, including old create/list still working).

- [ ] **Step 2b: One-time cleanup script.** `scripts/capitalize_tags.py` (same style as `scripts/migrate_mongo_to_pg.py`): dry-run by default, `--apply` to write, prints counts (changed, already fine, skipped for clash with the names). One transaction per user, idempotent, touches only `expense_entry_tags.name`. Tests on the dev test DB: dry-run changes nothing, apply capitalizes, clash skipped and reported, second run is a no-op, other users unaffected. No Alembic migration (a script can report and skip; a migration cannot).

- [ ] **Step 3: MCP tools.** In `mcp_server/server.py`: `rename_tag`, `delete_tag(tag, confirm=False)` (two-phase as in SPEC), `list_tags` shows count. Resolve by name via existing `_tags()` helper, validate input, destructive wording in the docstring. Update `mcp_server/README.md`. Tests: mock `client.request_json` and check (a) rename resolves name and calls PATCH, (b) `delete_tag` without confirm makes NO DELETE call and returns the count, (c) with confirm calls DELETE, (d) unknown name gives a clear error. *Check first how (or whether) the MCP module can be imported in tests; if not, add a minimal test setup and log it.*

- [ ] **Step 4: Chatbot tools (UPGRADE, they already exist).** Found while building Step 1: `rename_tag(old_name, new_name)` and `delete_tag(name)` already exist in `build_tools` with `interrupt()` confirmation, are in `_TOOL_CATEGORIES["tag"]` and the prompt. Keep their names and parameters. Upgrade them: use `tag_service.get_tag_by_name` instead of the private `_resolve_tag_id` scan; `delete_tag` puts "used by N entries, they will lose the tag" in the confirmation summary and the final reply; `rename_tag` says what the saved name will be ("Food", after the capitalization rule) and handles clashes and empty names cleanly; `create_tag` also handles an empty name (today a `ValidationError` escapes); `list_tags` shows counts. Update `create_tag` reply to show the saved name (already does). Tests: before approval nothing changes; approve -> changes; decline -> "Cancelled" and nothing changes; unknown tag message. *Check how existing agent tests (if any) drive `interrupt`; otherwise call the tool with a stubbed `interrupt` and log it.*

- [ ] **Step 4b: UI design draft, APPROVAL GATE (no UI code before this).** Rule: "Design or craft request: make a visual draft first (an Artifact) and wait for proceed". A first draft exists (https://claude.ai/artifact/BsZnGBss1Ho18gq1svhMAL, desktop dialog + phone bottom sheet) but it is OUTDATED. Refresh it before asking for approval: capitalized tag names ("Food", not "food"), the "Will be saved as Food" hint under the add/rename input, an empty state ("No tags yet. Type a name above."), a no-match state ("Add 'Xyz'"), an inline error state (name already exists), a loading state, a light-mode check, and a tablet width. Show it to the user and wait for an explicit approval of the updated draft. Record the approval (date, what changed) in this plan. Steps 5 and 6 do not start until then. Any later design change goes back through the draft first.

- [ ] **Step 5: Frontend store.** (needs Step 0's FRONTEND branch; approved draft from Step 4b not required for store logic, but do not start UI components before it) `useStore.js` actions: `fetchEntryTags` (adds count), `renameTag`, `deleteTag` (optimistic with rollback), and cleanup of `activeTagFilter`, `searchSelectedTags`, `searchExcludeTags`, `defaultExcludedTags`, plus expense re-fetch. Existing `createNewTag` keeps working.

- [ ] **Step 6: Frontend dialog.** (REQUIRES the approved draft from Step 4b.) `ManageTagsDialog.jsx` (per the approved Artifact draft), entry point in `Sidebar.jsx` tag section, phone bottom sheet via `usePhoneScreen`, CSS in `index.css` with variables only. Verify in the browser at phone and desktop width (and tablet unchanged).

- [ ] **Step 7: End-to-end check.** (includes: the cleanup script dry-run and apply against the local dev DB) Run API + UI locally: full flow in the dialog; live MCP run with a real client (rename, delete without confirm, delete with confirm); real chatbot rename and delete conversation (decline once, approve once).

- [ ] **Step 8: Wrap-up.** `uv run pytest`, `uv run ruff check .`. Update plan status. Add lessons to a skill (candidate: a new `add-crud-everywhere` skill: service, REST, MCP, chatbot, UI, tests). Update CLAUDE.md if anything about the project changed. No migration and nothing to run by hand on EC2.

## Deploy notes
- No Alembic migration. Deploy backend first, then frontend (UI calls the new endpoints).
- After the backend deploy, run the cleanup by hand on EC2: first `docker exec stalkmymoney_api uv run python scripts/capitalize_tags.py` (dry-run, read the report), then the same with `--apply`. It only renames tags; it deletes nothing. Back up or snapshot first if you want a safety net.
- MCP container is a separate image: redeploy it too so claude.ai sees the new tools.

## Decisions taken (user said "go with all your recommendations")
1. MCP `delete_tag` uses a `confirm` flag, kept for tags only. Retrofitting the other MCP delete tools is a later, separate job.
2. Capitalize the first letter only, on create and rename, in the service (see SPEC). Create's duplicate check is case-insensitive.
3. Existing tags: Option B, a one-time dry-run-first script that skips clashes (Step 2b).

Still open: the Artifact draft shows lowercase tag names; refresh it to capitalized names (and add the "Will be saved as ..." hint) before or at the start of Step 6.

## Problems log
Add an entry the moment something breaks. Format: What happened / Cause / Fix / General or one-off?

- **What happened:** the plan/spec said the chatbot had no `rename_tag`/`delete_tag` and that `update_tag`/`delete_tag` had no callers. **Cause:** my first look at `tools.py` was cut off (`head -80`), so I missed them. **Fix:** Step 4 is now an upgrade of the existing tools; the compatibility fix was done in Step 1. **General?** yes: grep the whole file for a name before claiming something is missing.
- **What happened:** changing `delete_tag` to return a count made the old chatbot check `if ok` treat 0 as "not found". **Cause:** 0 is falsy. **Fix:** compare with `is not None`. **General?** yes: when a bool-returning method starts returning a count, check every caller.
- **What happened:** Step 1 code was written on `master` with no feature branch. **Cause:** the Branches rule was added to the `CLAUDE.md` files after Step 1. **Fix:** Step 0 added at the top of the plan; the user decides how to move the uncommitted work onto `BACKEND-FEATURE-tags-crud`. **General?** yes: check the branch before the first edit of any feature.
- **Observation (no change made):** `expense_entry_tag_links` has no index on `tag_id` (the PK starts with `expense_entry_id`). The grouped count and the delete's count scan the links table. Fine for this app's size; adding an index would need a migration, which the spec excludes. Revisit if the table grows large.
