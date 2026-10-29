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

Write tools (create_expense, delete_expense, create_tag) call
`interrupt()` with a human-readable summary of the proposed action before
doing anything. That pauses the graph and hands control back to
AgentChatService, which surfaces the proposal to the frontend for the user
to approve or reject - nothing is written to the database until that
happens. Read tools (list_banks, list_tags, list_recent_expenses,
spending_summary) run immediately with no confirmation step.
"""

from typing import Optional

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bank_service import BankService
from app.services.expense_service import ExpenseService
from app.services.entry_tag_service import EntryTagService
from app.schemas.expense import ExpenseCreate
from app.schemas.expense_entry import ExpenseEntryCreate
from app.schemas.entry_tag import EntryTagCreate
from app.schemas.common import AdvancedSearchParams


def build_tools(user_id: str, db: AsyncSession) -> list:
    """Build a fresh set of tool instances bound to this one request's
    user_id and DB session via closure. Call this once per chat turn."""

    bank_service = BankService(db)
    expense_service = ExpenseService(db)
    tag_service = EntryTagService(db)

    async def _resolve_bank_id(bank_name: str) -> Optional[str]:
        banks = await bank_service.get_banks(user_id, name=bank_name)
        return banks[0].id if banks else None

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
    async def create_expense(
        bank_name: str, amount: float, description: str, is_topup: bool = False
    ) -> str:
        """Propose adding a new expense (or a topup/credit if is_topup is
        True) to a bank account, dated today. This only PROPOSES the
        action - it always asks the user to confirm first, and does
        nothing until they approve. Never tell the user an expense was
        added without calling this tool and getting back a success
        message; if the result says cancelled, tell them it was cancelled."""
        bank_id = await _resolve_bank_id(bank_name)
        if bank_id is None:
            return f"No bank account named '{bank_name}' found. Try list_banks."

        decision = interrupt(
            {
                "tool": "create_expense",
                "summary": (
                    f"Add {'a topup of' if is_topup else 'an expense of'} "
                    f"₹{abs(amount):.2f} ({description}) to {bank_name}"
                ),
                "args": {
                    "bank_name": bank_name,
                    "amount": amount,
                    "description": description,
                    "is_topup": is_topup,
                },
            }
        )
        if decision != "approve":
            return "Cancelled - the user did not approve this action."

        signed_amount = -abs(amount) if is_topup else abs(amount)
        expense_data = ExpenseCreate(
            bank_id=bank_id,
            expenses=[
                ExpenseEntryCreate(
                    amount=signed_amount,
                    description=description,
                    entry_tags=[],
                    type="topup" if is_topup else "expense",
                )
            ],
        )
        try:
            expense = await expense_service.create_expense(user_id, expense_data)
        except ValueError as e:
            return f"Failed: {e}"
        return f"Added successfully (expense id={expense.id})."

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
        spending_summary,
        create_expense,
        delete_expense,
        create_tag,
    ]
