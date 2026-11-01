"""
Tools for the agentic chat assistant (PLAN.md / agent migration).

Unlike the old Text-to-SQL chat (app/services/chat/), the LLM here never
generates SQL or any other code - it can only call these pre-defined
Python functions with typed arguments. `user_id` is captured in a closure
by `build_tools()` and is never an argument the LLM can set, so there is no
way for a prompt to make a tool act on another user's data; every tool
goes through the same service layer (BankService, ExpenseService,
EntryTagService) the REST API itself uses, which already scopes every
query by user_id.

Most tools here are write tools that call `interrupt()` with a
human-readable summary of the proposed action before doing anything. That
pauses the graph and hands control back to AgentChatService, which
surfaces the proposal to the frontend for the user to approve or reject -
nothing is written to the database until that happens. Exceptions:
- Read-only tools (list_banks, list_tags, list_recent_expenses,
  search_expenses, export_expenses, spending_summary) run immediately,
  nothing to confirm.
- Display-preference tools (set_dark_mode, set_privacy_mode,
  set_page_size, reorder_banks) also run immediately without a pause -
  they're reversible UI settings, not financial data, so a confirmation
  step would just be friction.
"""

from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bank_service import BankService
from app.services.expense_service import ExpenseService
from app.services.entry_tag_service import EntryTagService
from app.services.user_preference_service import UserPreferenceService
from app.schemas.bank import BankCreate, BankUpdate
from app.schemas.expense import ExpenseCreate
from app.schemas.expense_entry import ExpenseEntryCreate, ExpenseEntryUpdate
from app.schemas.entry_tag import EntryTagCreate, EntryTagUpdate
from app.schemas.user_preference import UserPreferenceUpdate
from app.schemas.common import AdvancedSearchParams


def build_tools(user_id: str, db: AsyncSession, export_box: Optional[dict] = None) -> list:
    """Build a fresh set of tool instances bound to this one request's
    user_id and DB session via closure. Call this once per chat turn.

    `export_box`: an optional dict the caller provides to receive a
    generated export file, if export_expenses is called this turn (see
    that tool below). It's a side-channel, not the tool's return value,
    specifically so the LLM never has to see or repeat the file's
    base64-encoded bytes in its own context - that would both burn a
    huge number of tokens and risk the model paraphrasing/truncating
    binary data. The tool returns a short confirmation string instead;
    AgentChatService reads export_box after the graph run and attaches
    its contents to the HTTP response directly."""

    bank_service = BankService(db)
    expense_service = ExpenseService(db)
    tag_service = EntryTagService(db)
    preference_service = UserPreferenceService(db)

    async def _resolve_bank_id(bank_name: str) -> Optional[str]:
        banks = await bank_service.get_banks(user_id, name=bank_name)
        return banks[0].id if banks else None

    async def _resolve_tag_id(tag_name: str) -> Optional[str]:
        tags = await tag_service.get_tags(user_id)
        for t in tags:
            if t.name.lower() == tag_name.lower():
                return t.id
        return None

    async def _add_single_entry(
        bank_id: str, amount: float, description: str, is_topup: bool, date_str: Optional[str] = None
    ) -> str:
        """Add one entry to the given day's expense for bank_id (today, if
        date_str is None). If that day already has an expense row for this
        bank (e.g. the user asked the chatbot to add something earlier
        that same day, or added one via the UI), the entry is appended to
        that same row via add_expense_entries instead of going through
        create_expense again - which defaults to "now" with second/
        microsecond precision and would otherwise silently create a
        second, separate expense row for the same calendar day every time
        this is called. Returns the expense id."""
        signed_amount = -abs(amount) if is_topup else abs(amount)
        entry = ExpenseEntryCreate(
            amount=signed_amount,
            description=description,
            entry_tags=[],
            type="topup" if is_topup else "expense",
        )
        date_str = date_str or datetime.now(timezone.utc).strftime("%d/%m/%Y")
        existing_id = await expense_service.find_expense_id_for_day(user_id, bank_id, date_str)
        if existing_id:
            result = await expense_service.add_expense_entries(user_id, existing_id, [entry])
            return result["id"]
        expense_data = ExpenseCreate(bank_id=bank_id, created_at=date_str, expenses=[entry])
        expense = await expense_service.create_expense(user_id, expense_data)
        return expense.id

    def _parse_optional_date(date_str: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Validates an optional DD/MM/YYYY date string the LLM supplied.
        Returns (normalized_date_str_or_None, error_message_or_None) - on
        error, the caller should return the error message as the tool
        result instead of proceeding."""
        if not date_str:
            return None, None
        try:
            parsed = datetime.strptime(date_str.strip(), "%d/%m/%Y")
        except ValueError:
            return None, f"Couldn't understand the date '{date_str}' - use DD/MM/YYYY."
        if parsed.date() > datetime.now(timezone.utc).date():
            return None, f"'{date_str}' is in the future - expenses can only be logged for today or earlier."
        return parsed.strftime("%d/%m/%Y"), None

    @tool
    async def list_banks() -> str:
        """List all of the user's bank accounts with their current balance."""
        banks = await bank_service.get_banks(user_id)
        if not banks:
            return "No bank accounts found."
        return "\n".join(
            f"- {b.name}: current balance ₹{b.current_balance:.2f}, "
            f"total disbursed ₹{b.total_disbursed_till_now:.2f}"
            for b in banks
        )

    @tool
    async def list_tags() -> str:
        """List all of the user's expense tags."""
        tags = await tag_service.get_tags(user_id)
        if not tags:
            return "No tags found."
        return "\n".join(f"- {t.name}" for t in tags)

    @tool
    async def list_recent_expenses(
        bank_name: Optional[str] = None, limit: int = 10
    ) -> str:
        """List the user's most recent expenses, optionally filtered to one
        bank account by name. Returns each expense's id (needed to delete
        it later - call this before delete_expense to find the right id),
        date, bank, total, and individual entries."""
        bank_id = None
        if bank_name:
            bank_id = await _resolve_bank_id(bank_name)
            if bank_id is None:
                return f"No bank account named '{bank_name}' found. Try list_banks."

        params = AdvancedSearchParams(
            bank_id=bank_id, page_number=1, per_page=min(max(limit, 1), 20)
        )
        expenses, total, non_topup, topup = await expense_service.get_expenses(
            user_id, params
        )
        if not expenses:
            return "No expenses found."

        lines = [f"Showing {len(expenses)} of {total} total expenses:"]
        for e in expenses:
            date_str = e["created_at"].strftime("%d %b %Y")
            entries_desc = ", ".join(
                f"{en['description']} (₹{en['amount']:.2f})" for en in e["expenses"]
            )
            lines.append(
                f"- id={e['id']} | {date_str} | {e['bank_name']} | "
                f"total ₹{e['expense_total']:.2f} | entries: {entries_desc}"
            )
        return "\n".join(lines)

    @tool
    async def spending_summary(bank_name: Optional[str] = None) -> str:
        """Get total spending grouped by tag - use this for 'how much did I
        spend on X' style questions. Optionally filtered to one bank
        account by name."""
        bank_id = None
        if bank_name:
            bank_id = await _resolve_bank_id(bank_name)
            if bank_id is None:
                return f"No bank account named '{bank_name}' found. Try list_banks."

        data = await expense_service.get_aggregated_data(user_id, bank_id)
        if not data:
            return "No tagged spending data found."
        return "\n".join(
            f"- {v['tag_name']}: ₹{v['tags_wise_summation']:.2f}"
            for v in data.values()
        )

    @tool
    async def search_expenses(
        keyword: Optional[str] = None,
        tag_name: Optional[str] = None,
        bank_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        limit: int = 20,
    ) -> str:
        """Search the user's expenses with any combination of filters: a
        keyword in the description, a tag name, a bank account name, a
        date range (start_date/end_date as DD/MM/YYYY, end_date optional),
        and/or a min/max entry amount. Use this for conversational
        questions like "show me everything over 500 in October" or "what
        did I spend on 'travel' last month" - all filters are optional and
        combine with AND. Read-only, no confirmation needed."""
        bank_id = None
        if bank_name:
            bank_id = await _resolve_bank_id(bank_name)
            if bank_id is None:
                return f"No bank account named '{bank_name}' found. Try list_banks."
        tag_id = None
        if tag_name:
            tag_id = await _resolve_tag_id(tag_name)
            if tag_id is None:
                return f"No tag named '{tag_name}' found. Try list_tags."

        advanced = bool(keyword or tag_id or start_date)
        search_kwargs = {"advanced_search": advanced, "per_page": min(max(limit, 1), 50)}
        if advanced:
            if keyword:
                search_kwargs["search_by_keyword"] = keyword
            if tag_id:
                search_kwargs["search_by_tags"] = [tag_id]
            if bank_id:
                search_kwargs["search_by_bank_ids"] = [bank_id]
            if start_date:
                search_kwargs["search_by_daterange"] = {
                    "start_date": start_date,
                    "end_date": end_date,
                }
        elif bank_id:
            search_kwargs["bank_id"] = bank_id

        params = AdvancedSearchParams(**search_kwargs)
        found_expenses, total, _, _ = await expense_service.get_expenses(user_id, params)
        if not found_expenses:
            return "No matching expenses found."

        lines = [f"Showing {len(found_expenses)} of {total} matching expenses:"]
        shown = 0
        for e in found_expenses:
            matching_entries = [
                en
                for en in e["expenses"]
                if (min_amount is None or abs(en["amount"]) >= min_amount)
                and (max_amount is None or abs(en["amount"]) <= max_amount)
            ]
            if not matching_entries:
                continue
            date_str = e["created_at"].strftime("%d %b %Y")
            entries_desc = ", ".join(
                f"{en['description']} (₹{en['amount']:.2f})" for en in matching_entries
            )
            lines.append(
                f"- id={e['id']} | {date_str} | {e['bank_name']} | entries: {entries_desc}"
            )
            shown += 1
        if shown == 0:
            return "No matching expenses found."
        return "\n".join(lines)

    @tool
    async def export_expenses(
        keyword: Optional[str] = None,
        tag_name: Optional[str] = None,
        bank_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        top_n: Optional[int] = None,
        format: str = "pdf",
    ) -> str:
        """Export the user's expenses as a real downloadable file - use
        this whenever they ask to export/download/save their expenses,
        as opposed to search_expenses which just answers in chat. Same
        filters as search_expenses (all optional, combine with AND):
        keyword in the description, tag name, bank account name, a date
        range (start_date/end_date as DD/MM/YYYY), and/or min/max entry
        amount. `top_n`: set this whenever the user asks for "top N" /
        "last N" / "most recent N" expenses (e.g. "top 5 junkfood
        expenses") - keeps only the N MOST RECENT entries (today first,
        then yesterday, then earlier - by date, never by amount) AFTER
        every other filter is applied. Without top_n, every matching
        entry is included (this is the bug to avoid: a plain "download
        my junkfood expenses" should NOT be quietly truncated, only an
        explicit "top N" request should be).
        `format` is "pdf" (default) or "csv". Read-only, no confirmation
        needed - exports up to 100 matching expense groups (each of
        which may have several entries, so often more than 100
        individual line items) before any top_n cap is applied."""
        if format not in ("pdf", "csv"):
            return "format must be 'pdf' or 'csv'."

        bank_id = None
        if bank_name:
            bank_id = await _resolve_bank_id(bank_name)
            if bank_id is None:
                return f"No bank account named '{bank_name}' found. Try list_banks."
        tag_id = None
        if tag_name:
            tag_id = await _resolve_tag_id(tag_name)
            if tag_id is None:
                return f"No tag named '{tag_name}' found. Try list_tags."

        advanced = bool(keyword or tag_id or start_date)
        search_kwargs = {"advanced_search": advanced, "per_page": 100}
        if advanced:
            if keyword:
                search_kwargs["search_by_keyword"] = keyword
            if tag_id:
                search_kwargs["search_by_tags"] = [tag_id]
            if bank_id:
                search_kwargs["search_by_bank_ids"] = [bank_id]
            if start_date:
                search_kwargs["search_by_daterange"] = {
                    "start_date": start_date,
                    "end_date": end_date,
                }
        elif bank_id:
            search_kwargs["bank_id"] = bank_id

        params = AdvancedSearchParams(**search_kwargs)
        found_expenses, total, _, _ = await expense_service.get_expenses(user_id, params)

        rows = []
        for e in found_expenses:
            for en in e["expenses"]:
                amount = en["amount"]
                if min_amount is not None and abs(amount) < min_amount:
                    continue
                if max_amount is not None and abs(amount) > max_amount:
                    continue
                rows.append(
                    {
                        "date": e["created_at"].strftime("%d/%m/%Y"),
                        "bank": e["bank_name"],
                        "description": en["description"] or "(no description)",
                        "amount": amount,
                    }
                )
        if not rows:
            return "No matching expenses to export."

        matched_count = len(rows)
        if top_n is not None and top_n > 0:
            from datetime import datetime as _datetime

            # Most recent N, not highest-amount N - "top N" means recency
            # to the user (today first, then yesterday, then earlier).
            rows.sort(key=lambda r: _datetime.strptime(r["date"], "%d/%m/%Y"), reverse=True)
            rows = rows[:top_n]

        from app.services.agent.export import build_export
        import base64

        title_bits = [b for b in [tag_name, bank_name, keyword] if b]
        title_bits_str = ", ".join(title_bits)
        if top_n is not None:
            title = f"Top {len(rows)} Expenses" + (f" - {title_bits_str}" if title_bits_str else "")
        else:
            title = ("Expenses - " + title_bits_str) if title_bits_str else "Expenses"
        content, filename, mime_type = build_export(rows, title, format)

        if export_box is not None:
            export_box["filename"] = filename
            export_box["mime_type"] = mime_type
            export_box["content_b64"] = base64.b64encode(content).decode("ascii")

        return (
            f"Exported {len(rows)} of {matched_count} matching entries "
            f"as {filename} - ready to download."
        )

    @tool
    async def create_expense(
        bank_name: str,
        amount: float,
        description: str,
        is_topup: bool = False,
        date: Optional[str] = None,
    ) -> str:
        """Propose adding a new expense (or a topup/credit if is_topup is
        True) to a bank account. date is optional, as DD/MM/YYYY - omit it
        to use today; it must not be in the future. This only PROPOSES the
        action - it always asks the user to confirm first, and does
        nothing until they approve. Never tell the user an expense was
        added without calling this tool and getting back a success
        message; if the result says cancelled, tell them it was cancelled."""
        bank_id = await _resolve_bank_id(bank_name)
        if bank_id is None:
            return f"No bank account named '{bank_name}' found. Try list_banks."
        normalized_date, date_error = _parse_optional_date(date)
        if date_error:
            return date_error

        decision = interrupt(
            {
                "tool": "create_expense",
                "summary": (
                    f"Add {'a topup of' if is_topup else 'an expense of'} "
                    f"₹{abs(amount):.2f} ({description}) to {bank_name}"
                    + (f" on {normalized_date}" if normalized_date else "")
                ),
                "args": {
                    "bank_name": bank_name,
                    "amount": amount,
                    "description": description,
                    "is_topup": is_topup,
                    "date": normalized_date,
                },
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."

        try:
            expense_id = await _add_single_entry(
                bank_id, amount, description, is_topup, normalized_date
            )
        except ValueError as e:
            return f"Failed: {e}"
        return f"Added successfully (expense id={expense_id})."

    @tool
    async def transfer_money(
        from_bank: str,
        to_bank: str,
        amount: float,
        description: str = "Transfer",
        date: Optional[str] = None,
    ) -> str:
        """Propose transferring money from one of the user's bank accounts to
        another - use this instead of two separate create_expense calls
        whenever the user asks to "transfer"/"move"/"send" money between
        their own accounts, so both the debit and the credit happen as one
        confirmed action instead of two independent ones. date is
        optional, as DD/MM/YYYY - omit it to use today; it must not be in
        the future. This only PROPOSES the action - it asks the user to
        confirm once, then debits from_bank and credits to_bank together.
        Does nothing until approved."""
        from_id = await _resolve_bank_id(from_bank)
        if from_id is None:
            return f"No bank account named '{from_bank}' found. Try list_banks."
        to_id = await _resolve_bank_id(to_bank)
        if to_id is None:
            return f"No bank account named '{to_bank}' found. Try list_banks."
        if from_id == to_id:
            return "from_bank and to_bank must be different accounts."
        normalized_date, date_error = _parse_optional_date(date)
        if date_error:
            return date_error

        decision = interrupt(
            {
                "tool": "transfer_money",
                "summary": (
                    f"Transfer ₹{abs(amount):.2f} ({description}) "
                    f"from {from_bank} to {to_bank}"
                    + (f" on {normalized_date}" if normalized_date else "")
                ),
                "args": {
                    "from_bank": from_bank,
                    "to_bank": to_bank,
                    "amount": amount,
                    "description": description,
                    "date": normalized_date,
                },
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."

        try:
            debit_expense_id = await _add_single_entry(
                from_id, amount, description, False, normalized_date
            )
        except ValueError as e:
            return f"Failed before any money moved: {e}"

        try:
            credit_expense_id = await _add_single_entry(
                to_id, amount, description, True, normalized_date
            )
        except ValueError as e:
            return (
                f"Debited ₹{abs(amount):.2f} from {from_bank} (expense id="
                f"{debit_expense_id}) but crediting {to_bank} failed: {e}. "
                f"{from_bank} has already been debited - the user may need "
                f"to delete that expense or retry the credit manually."
            )
        return (
            f"Transferred successfully: debited {from_bank} (expense id="
            f"{debit_expense_id}), credited {to_bank} (expense id="
            f"{credit_expense_id})."
        )

    @tool
    async def delete_expense(expense_id: str) -> str:
        """Propose deleting an entire expense by its id - call
        list_recent_expenses first to find the right id, never guess one.
        This only PROPOSES the action and asks the user to confirm first;
        it does nothing until they approve."""
        decision = interrupt(
            {
                "tool": "delete_expense",
                "summary": f"Delete expense {expense_id}",
                "args": {"expense_id": expense_id},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        ok = await expense_service.delete_expense(user_id, expense_id)
        return "Deleted successfully." if ok else "Expense not found."

    @tool
    async def delete_expense_entry(expense_id: str, entry_id: str) -> str:
        """Propose deleting a single entry from an expense, leaving the
        rest of that day's other entries alone - use delete_expense
        instead if the whole day's expense should go. Call
        list_recent_expenses or search_expenses first to find the right
        expense_id/entry_id (entry_id is the ee_... value), never guess
        them. This only PROPOSES the action and asks the user to confirm
        first."""
        decision = interrupt(
            {
                "tool": "delete_expense_entry",
                "summary": f"Delete entry {entry_id} from expense {expense_id}",
                "args": {"expense_id": expense_id, "entry_id": entry_id},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        ok = await expense_service.delete_expense_entry(user_id, expense_id, entry_id)
        return "Entry deleted." if ok else "Entry not found."

    @tool
    async def edit_expense_entry(
        expense_id: str,
        entry_id: str,
        description: Optional[str] = None,
        tag_names: Optional[list[str]] = None,
    ) -> str:
        """Propose editing an existing expense entry's description and/or
        tags (the amount itself cannot be changed this way - delete the
        entry and add a new one if the amount is wrong). entry_id is the
        ee_... id from list_recent_expenses/search_expenses, never guess
        it. tag_names, if given, REPLACES the entry's tags entirely with
        that exact list - call list_tags first to use existing names, or
        create_tag first if the tag doesn't exist yet. This only PROPOSES
        the action and asks the user to confirm first."""
        tag_ids = None
        if tag_names is not None:
            tag_ids = []
            for name in tag_names:
                tid = await _resolve_tag_id(name)
                if tid is None:
                    return f"No tag named '{name}' found. Try list_tags or create_tag first."
                tag_ids.append(tid)

        summary = f"Edit entry {entry_id}"
        if description is not None:
            summary += f": description -> '{description}'"
        if tag_names is not None:
            summary += f", tags -> {tag_names}"

        decision = interrupt(
            {
                "tool": "edit_expense_entry",
                "summary": summary,
                "args": {
                    "expense_id": expense_id,
                    "entry_id": entry_id,
                    "description": description,
                    "tag_names": tag_names,
                },
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."

        result = await expense_service.update_expense_entry(
            user_id,
            ExpenseEntryUpdate(
                expense_id=expense_id,
                entry_id=entry_id,
                updated_description=description,
                entry_tags=tag_ids,
            ),
        )
        return "Entry updated." if result else "Entry not found."

    @tool
    async def bulk_delete_expenses_by_tag(
        tag_name: str,
        bank_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> str:
        """Propose deleting EVERY expense entry tagged with tag_name in one
        batch, optionally narrowed to one bank account and/or a date range
        (start_date/end_date as DD/MM/YYYY). Call list_tags first if
        unsure of the exact name. Shows exactly how many entries and how
        much money would be removed, and asks for ONE confirmation that
        covers the whole batch - never call delete_expense_entry
        repeatedly for this instead. Limited to the 100 most recent
        matching expense groups per call."""
        tag_id = await _resolve_tag_id(tag_name)
        if tag_id is None:
            return f"No tag named '{tag_name}' found. Try list_tags."
        bank_id = None
        if bank_name:
            bank_id = await _resolve_bank_id(bank_name)
            if bank_id is None:
                return f"No bank account named '{bank_name}' found. Try list_banks."

        search_kwargs = {
            "advanced_search": True,
            "search_by_tags": [tag_id],
            "per_page": 100,
        }
        if bank_id:
            search_kwargs["search_by_bank_ids"] = [bank_id]
        if start_date:
            search_kwargs["search_by_daterange"] = {"start_date": start_date, "end_date": end_date}
        params = AdvancedSearchParams(**search_kwargs)
        matched_expenses, _, _, _ = await expense_service.get_expenses(user_id, params)

        to_delete = []
        total_amount = 0.0
        for exp in matched_expenses:
            for entry in exp["expenses"]:
                if tag_id in entry["entry_tags"]:
                    to_delete.append((exp["id"], entry["ee_id"]))
                    total_amount += entry["amount"]

        if not to_delete:
            return f"No expenses found tagged '{tag_name}'."

        decision = interrupt(
            {
                "tool": "bulk_delete_expenses_by_tag",
                "summary": (
                    f"Delete {len(to_delete)} expense entr"
                    f"{'y' if len(to_delete) == 1 else 'ies'} tagged '{tag_name}'"
                    f" (total ₹{abs(total_amount):.2f})"
                    + (f" on {bank_name}" if bank_name else "")
                ),
                "args": {
                    "tag_name": tag_name,
                    "bank_name": bank_name,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."

        deleted = 0
        for expense_id, entry_id in to_delete:
            ok = await expense_service.delete_expense_entry(user_id, expense_id, entry_id)
            if ok:
                deleted += 1
        return f"Deleted {deleted} of {len(to_delete)} matching entries."

    @tool
    async def create_bank(name: str, initial_balance: float) -> str:
        """Propose creating a new bank account with a starting balance.
        This only PROPOSES the action and asks the user to confirm
        first."""
        decision = interrupt(
            {
                "tool": "create_bank",
                "summary": f"Create bank account '{name}' with balance ₹{initial_balance:.2f}",
                "args": {"name": name, "initial_balance": initial_balance},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        try:
            bank = await bank_service.create_bank(
                user_id,
                BankCreate(
                    name=name, initial_balance=initial_balance, current_balance=initial_balance
                ),
            )
        except Exception as e:
            return f"Failed: {e}"
        return f"Bank '{bank.name}' created (id={bank.id})."

    @tool
    async def rename_bank(bank_name: str, new_name: str) -> str:
        """Propose renaming one of the user's bank accounts. This only
        PROPOSES the action and asks the user to confirm first."""
        bank_id = await _resolve_bank_id(bank_name)
        if bank_id is None:
            return f"No bank account named '{bank_name}' found. Try list_banks."
        decision = interrupt(
            {
                "tool": "rename_bank",
                "summary": f"Rename bank '{bank_name}' to '{new_name}'",
                "args": {"bank_name": bank_name, "new_name": new_name},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        bank = await bank_service.update_bank(user_id, bank_id, BankUpdate(name=new_name))
        return f"Bank renamed to '{bank.name}'." if bank else "Bank not found."

    @tool
    async def set_bank_balance(bank_name: str, new_balance: float) -> str:
        """Propose directly correcting a bank account's current balance to
        an exact value (setting it outright, not adding/subtracting). Use
        this only to fix a wrong balance - for a normal expense, topup, or
        transfer, use create_expense or transfer_money instead, which
        keep the expense history consistent with the balance. This only
        PROPOSES the action and asks the user to confirm first."""
        bank_id = await _resolve_bank_id(bank_name)
        if bank_id is None:
            return f"No bank account named '{bank_name}' found. Try list_banks."
        decision = interrupt(
            {
                "tool": "set_bank_balance",
                "summary": f"Set {bank_name}'s balance to ₹{new_balance:.2f}",
                "args": {"bank_name": bank_name, "new_balance": new_balance},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        bank = await bank_service.update_bank(
            user_id, bank_id, BankUpdate(current_balance=new_balance)
        )
        return f"{bank.name}'s balance is now ₹{bank.current_balance:.2f}." if bank else "Bank not found."

    @tool
    async def delete_bank(bank_name: str) -> str:
        """Propose permanently deleting a bank account AND all of its
        expense history - this cannot be undone. This only PROPOSES the
        action and asks the user to confirm first."""
        bank_id = await _resolve_bank_id(bank_name)
        if bank_id is None:
            return f"No bank account named '{bank_name}' found. Try list_banks."
        decision = interrupt(
            {
                "tool": "delete_bank",
                "summary": f"Permanently delete bank '{bank_name}' and all of its expense history",
                "args": {"bank_name": bank_name},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        ok = await bank_service.delete_bank(user_id, bank_id)
        return f"Bank '{bank_name}' deleted." if ok else "Bank not found."

    @tool
    async def rename_tag(old_name: str, new_name: str) -> str:
        """Propose renaming an existing expense tag. This only PROPOSES
        the action and asks the user to confirm first."""
        tag_id = await _resolve_tag_id(old_name)
        if tag_id is None:
            return f"No tag named '{old_name}' found. Try list_tags."
        decision = interrupt(
            {
                "tool": "rename_tag",
                "summary": f"Rename tag '{old_name}' to '{new_name}'",
                "args": {"old_name": old_name, "new_name": new_name},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        tag = await tag_service.update_tag(user_id, tag_id, EntryTagUpdate(name=new_name))
        return f"Tag renamed to '{tag.name}'." if tag else "Tag not found."

    @tool
    async def delete_tag(name: str) -> str:
        """Propose deleting an expense tag itself (expenses that used it
        stay, just untagged). This only PROPOSES the action and asks the
        user to confirm first."""
        tag_id = await _resolve_tag_id(name)
        if tag_id is None:
            return f"No tag named '{name}' found. Try list_tags."
        decision = interrupt(
            {
                "tool": "delete_tag",
                "summary": f"Delete tag '{name}'",
                "args": {"name": name},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        ok = await tag_service.delete_tag(user_id, tag_id)
        return f"Tag '{name}' deleted." if ok else "Tag not found."

    @tool
    async def set_dark_mode(enabled: bool) -> str:
        """Turn dark mode on or off. Applies immediately - it's a display
        preference, not a data change, so no confirmation is needed."""
        await preference_service.update_preferences(
            user_id, UserPreferenceUpdate(is_dark_mode=enabled)
        )
        return f"Dark mode turned {'on' if enabled else 'off'}."

    @tool
    async def set_privacy_mode(enabled: bool) -> str:
        """Turn privacy mode (hides amounts on screen) on or off. Applies
        immediately, no confirmation needed."""
        await preference_service.update_preferences(
            user_id, UserPreferenceUpdate(privacy_mode_enabled=enabled)
        )
        return f"Privacy mode turned {'on' if enabled else 'off'}."

    @tool
    async def set_page_size(page_size: int) -> str:
        """Change how many expenses are shown per page (1-100). Applies
        immediately, no confirmation needed."""
        page_size = min(max(page_size, 1), 100)
        await preference_service.update_preferences(
            user_id, UserPreferenceUpdate(page_size=page_size)
        )
        return f"Page size set to {page_size}."

    @tool
    async def reorder_banks(bank_names_in_order: list[str]) -> str:
        """Reorder how the user's bank accounts are displayed, given their
        names in the desired order. Banks not mentioned keep their
        relative order after the ones listed. Applies immediately, no
        confirmation needed."""
        ids_in_order = []
        for name in bank_names_in_order:
            bid = await _resolve_bank_id(name)
            if bid is None:
                return f"No bank account named '{name}' found. Try list_banks."
            ids_in_order.append(bid)
        all_banks = await bank_service.get_banks(user_id)
        remaining = [b.id for b in all_banks if b.id not in ids_in_order]
        await preference_service.update_preferences(
            user_id, UserPreferenceUpdate(banks_display_order=ids_in_order + remaining)
        )
        return "Bank display order updated."

    @tool
    async def create_tag(name: str) -> str:
        """Propose creating a new expense tag. This only PROPOSES the
        action and asks the user to confirm first; it does nothing until
        they approve."""
        decision = interrupt(
            {
                "tool": "create_tag",
                "summary": f"Create tag '{name}'",
                "args": {"name": name},
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."
        try:
            tag = await tag_service.create_tag(user_id, EntryTagCreate(name=name))
        except ValueError as e:
            return f"Failed: {e}"
        return f"Tag '{tag.name}' created."

    return [
        list_banks,
        list_tags,
        list_recent_expenses,
        search_expenses,
        export_expenses,
        spending_summary,
        create_expense,
        transfer_money,
        delete_expense,
        delete_expense_entry,
        edit_expense_entry,
        bulk_delete_expenses_by_tag,
        create_bank,
        rename_bank,
        set_bank_balance,
        delete_bank,
        create_tag,
        rename_tag,
        delete_tag,
        set_dark_mode,
        set_privacy_mode,
        set_page_size,
        reorder_banks,
    ]
