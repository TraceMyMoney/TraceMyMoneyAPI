# SPEC: Tags CRUD (manage tags in the UI, MCP and chatbot)

Status: SPEC written, waiting for the user's "proceed" (design draft first, no code yet).

## 1. What

Let a user fully manage their expense tags: see them with usage counts, create, rename, delete.
Today only create and list exist (`GET /entry-tags/`, `POST /entry-tags/create`, `CreateTagDialog`,
MCP `list_tags`/`create_tag`, chatbot `list_tags`). `EntryTagService` already has `update_tag` and
`delete_tag`, but nothing calls them.

Same feature must reach all four surfaces (backend rule in `TraceMyMoneyAPI/CLAUDE.md`):
REST API, UI dialog, MCP tools, chatbot tools. All use the same service layer.

## 2. Rules

### Data and API
- Every query filters by `user_id`. A tag of another user is "not found" (404), never "forbidden".
- Name: trimmed, 1-50 characters, validated in the schema. Duplicate check is case-insensitive per user
  (`Food` and `food` are the same tag). The DB unique constraint stays as a safety net; a clash
  must return 400 with a clear `detail`, never a 500.
- **Capitalization rule:** on create AND rename, the service trims the name, collapses repeated spaces and
  upper-cases only the FIRST letter; the rest stays as typed ("food" -> "Food", "rent and bills" ->
  "Rent and bills", "EMI" stays "EMI", "upi" -> "Upi"). One shared helper in `EntryTagService`, so REST, UI,
  MCP and chatbot (including tags the chatbot creates while adding an expense) all behave the same.
  Matching stays case-insensitive everywhere, so users never need to type the exact case.
  The duplicate check on create is now case-insensitive too (today it is exact-match).
  The UI shows what will be saved ("Will be saved as Food") and the API returns the saved name.
- Renaming a tag to its own name (or only a different case of it) is allowed and is not a clash.
- **One-time cleanup of existing tags (Option B):** script `scripts/capitalize_tags.py`, dry-run by default,
  `--apply` to write. It capitalizes each existing tag's first letter, per user, in one transaction per user.
  It SKIPS and reports any tag whose new name would clash with another of that user's tags (for example
  `food` and `Food` both exist); merging those is out of scope and left to the user. It never touches
  entries, links or amounts. Safe to run twice. Run by hand on production after the deploy (dry-run first),
  since deploys do not run scripts or migrations.
- List returns `id, name, created_at, entry_count`, sorted by name (case-insensitive).
  `entry_count` comes from one grouped query (no N+1).
- New endpoints: `PATCH /entry-tags/{tag_id}` (rename) and `DELETE /entry-tags/{tag_id}`.
  Existing `GET /entry-tags/` and `POST /entry-tags/create` keep working (the UI already uses them);
  `GET` only gains the extra `entry_count` field.
- Delete is one transaction: delete the tag (links cascade) AND remove its id from
  `user_preferences.default_excluded_tags` (that array has no foreign key, so it would keep a dead id).
- The delete response says how many entries lost the tag (`entries_untagged`).
- No schema change, so no Alembic migration. Existing entries keep all other tags and their amounts.
  Deleting a tag never deletes an expense or entry.

### "Tag is used by N entries" warning
| Surface | How the warning works |
|---|---|
| UI dialog | Each row shows its count. The delete confirmation says "Used by N entries. They will lose this tag. Entries and amounts stay." For a tag used by 0 entries, delete is one tap with no extra confirm. |
| REST API | No warning step (API is for programs). `DELETE` just deletes and returns `entries_untagged`. |
| MCP `delete_tag` | MCP has no confirm step, so the tool has one. `delete_tag(tag, confirm=False)` does NOT delete: it returns `{needs_confirmation: true, entries_affected: N}`. Claude must tell the user the count, and only after a yes call again with `confirm=true`. Docstring says DESTRUCTIVE. |
| Chatbot `delete_tag` | Resolves the name, reads the count, then pauses at the agent's `interrupt()` confirmation step with summary "Delete tag 'food' (used by N entries, they will lose the tag)". Nothing happens until the user approves. |

### MCP tools (`mcp_server/server.py`, `mcp_server/README.md`)
- `rename_tag(tag, new_name)`: names, not ids. Matching the tag is case-insensitive. Not destructive.
- `delete_tag(tag, confirm=False)`: as in the table. Destructive.
- `list_tags` now returns the usage count too.
- Inputs validated in the tool (empty name, over 50 characters) before calling the API.

### Chatbot tools (`app/services/agent/tools.py`, `agent_service.py`)
- `rename_tag(tag_name, new_name)`: changes data, so it goes through the confirmation step.
  Summary: "Rename tag 'food' to 'groceries'".
- `delete_tag(tag_name)`: confirmation step with the usage count (see table).
- `list_tags` (already always included) also shows the usage count.
- Add both to the right tool category in `_TOOL_CATEGORIES` (not `_ALWAYS_INCLUDED_TOOLS`, they are
  rare actions) and mention them in the agent prompt. Tools call `EntryTagService`, no copied logic.

### UI (`TraceMyMoneyUI`)
- A "Manage tags" dialog opened from the Sidebar tag section (and reachable on phone from the same
  place the tag filter lives). New component `ManageTagsDialog.jsx`; `CreateTagDialog` stays as is.
- Contents: search box, "add tag" row, list of tags (name, count, rename, delete).
- Rename is inline (tap the pencil or the name, Enter saves, Escape cancels). Optimistic update with
  rollback and a toast on error. Typed text is kept when something fails.
- All calls go through new store actions in `useStore.js` (never Axios in components).
- After rename or delete the store refreshes `entryTags` and fixes anything that references the tag:
  the sidebar filter (`activeTagFilter`), `searchSelectedTags`, `searchExcludeTags`,
  `defaultExcludedTags`. Expense rows already on screen are re-fetched so removed tags disappear.
- Phone: full-height bottom sheet, 44px tap targets, no horizontal scroll, delete is a swipe-free
  explicit button. Tablet and desktop: centred panel. Phone-only code gated on `usePhoneScreen`;
  tablet/desktop layout of the rest of the app unchanged.
- Uses CSS variables only (`--purple` for tags, `--red` for delete). Reduced motion respected.

## 3. Out of scope
- Merging two tags, tag colours or icons, reordering tags, bulk delete, undo after delete.
- Merging tags that clash after capitalization (the script only reports them).
- Changing the existing `bulk_delete_expenses_by_tag` chatbot tool (it deletes expenses, different thing).
- Pagination of the tag list (a user has tens of tags, not thousands; the list is one light query).
- MCP/chatbot tool to *create* a tag in the chatbot (chatbot creates tags while adding an expense;
  not changed here).
- Rate limiting (authenticated, cheap, user-scoped).

## 4. Done means
1. `uv run pytest` and `uv run ruff check .` pass (state any old known failure).
2. Tests prove: capitalization (first letter only, acronyms kept, extra spaces, same result via REST, MCP
   and chatbot, case-insensitive duplicate on create -> 400), cleanup script (dry-run changes nothing,
   `--apply` capitalizes, clashes skipped and reported, second run changes nothing),
   rename (ok, same name, case-only change, duplicate -> 400, other user's tag -> 404),
   delete (links removed, expenses kept, `default_excluded_tags` cleaned, other user's tag -> 404),
   list counts, MCP rename/delete including the `confirm` gate, chatbot rename/delete including that
   nothing changes before approval and nothing when declined.
3. In a real browser: rename and delete from the dialog on phone width and desktop width; sidebar
   filter and expense rows update; a deleted default-excluded tag no longer shows as excluded.
4. A live run of the MCP tools with a real client, and a real chatbot conversation for rename and delete.
5. `mcp_server/README.md` tool list updated. Plan status line updated, lessons added to a skill.
