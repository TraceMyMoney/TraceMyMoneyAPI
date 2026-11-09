"""
Agentic chat service (PLAN.md agent migration) - replaces the old
Text-to-SQL chat (app/services/chat/) with a LangGraph tool-calling agent.

Architecture, and why it's safe:
  - Tools (app/services/agent/tools.py) are plain Python functions, not
    LLM-generated SQL. The LLM can only call these with typed arguments;
    `user_id` is bound into each tool via closure and is never an argument
    the LLM controls, so there's no way for a prompt to make a tool act on
    another user's data.
  - Write tools (create_expense, delete_expense, create_tag) call
    `interrupt()` before doing anything, pausing the graph and handing a
    human-readable proposal back to the caller. Nothing is written until
    the user explicitly approves via `confirm()` below.
  - Conversation memory lives in a single process-wide `InMemorySaver`,
    keyed by thread_id. Since that's a shared cache across every user's
    conversations, a bare client-supplied thread_id is NOT trusted as the
    key on its own (two different users' frontends could in principle
    generate/guess the same id) - it's always namespaced with the
    authenticated user_id server-side first (_scoped_thread_id), so a
    collision can only ever land inside that same user's own history.
  - In-memory only: conversation state (including any pending
    confirmation) is lost on server restart. Acceptable for now; swap
    `InMemorySaver` for a persistent checkpointer if that becomes a
    problem.
"""

import logging
from datetime import datetime, timezone

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_llm
from app.schemas.user_preference import UserPreferenceUpdate
from app.services.agent.tools import build_tools
from app.services.bank_service import BankService
from app.services.entry_tag_service import EntryTagService
from app.services.jev_insights import (
    classify_chat_category,
    classify_fast_path,
    score_write_risk,
)
from app.services.user_preference_service import UserPreferenceService

logger = logging.getLogger(__name__)

# Maps a Jev-classified chat category to the extra (non-always-included)
# tool names it unlocks for that turn - see _build_graph. Purely a token-
# saving optimization (fewer tool schemas sent to the LLM per turn); when
# Jev is unavailable or unsure, every category falls back to the full
# tool list, identical to this feature not existing at all.
_ALWAYS_INCLUDED_TOOLS = {
    "list_banks",
    "list_tags",
    "list_recent_expenses",
    "search_expenses",
    "export_expenses",
    "email_expenses",
    "spending_summary",
    "set_dark_mode",
    "set_privacy_mode",
    "set_page_size",
    "reorder_banks",
}
_TOOL_CATEGORIES = {
    "expense": {
        "create_expense",
        "delete_expense",
        "delete_expense_entry",
        "edit_expense_entry",
        "bulk_delete_expenses_by_tag",
    },
    "transfer": {"transfer_money"},
    "bank": {"create_bank", "rename_bank", "set_bank_balance", "delete_bank"},
    "tag": {"create_tag", "rename_tag", "delete_tag"},
}

SYSTEM_PROMPT = """
You are the in-app assistant for "Stalk My Money", a personal expense
tracker. Be warm, concise, and conversational - 2-4 sentences unless the
user asks for a list. Always show money as ₹ (Indian Rupees).

Today's date is {today} (DD/MM/YYYY). Use this - not your training
cutoff, not a guess - as "today" everywhere: whether a date the user
gives is in the past (allowed) or future (not allowed), and what to fill
in when a tool's date argument is omitted. A past-dated expense (e.g.
logging something from last week) is completely normal and must be
logged without comment or pushback; only refuse a date that is strictly
after today's date above.

You have tools covering nearly everything the app itself can do:
- Look things up: list_banks, list_tags, list_recent_expenses,
  search_expenses (flexible filters: keyword/tag/bank/date range/amount),
  spending_summary.
- Download/export: export_expenses - use this (not search_expenses)
  whenever the user asks to download, export, or save their expenses as
  a file. Same filters as search_expenses; defaults to PDF, can do CSV
  too. It produces a real file the user's browser downloads - never
  paste CSV/table text into the chat yourself as a substitute for this.
  It NEVER sends email.
- Email a report: email_expenses - ONLY when the user explicitly says
  email/mail/"send to my inbox" (set user_asked_for_email=true). It sends
  the PDF to their own account email in the background. "download",
  "export", "give me a PDF" are NOT email requests - use export_expenses.
  If it is unclear whether they want a download or an email (e.g. "send
  me my expenses"), ask which one before doing anything.
- Expenses: create_expense (expense or topup), transfer_money (between
  two of the user's own banks), delete_expense (a whole day's expense),
  delete_expense_entry (just one entry within a day), edit_expense_entry
  (description/tags), bulk_delete_expenses_by_tag (delete every entry
  with a given tag in one batch). Both create_expense and transfer_money
  take an optional date (DD/MM/YYYY, today if omitted, never in the
  future) - the user CAN log a past expense, so never tell them logging
  is limited to today.
- Banks: create_bank, rename_bank, set_bank_balance (a direct correction,
  not a transaction), delete_bank (also deletes all its expense history).
- Tags: create_tag, rename_tag, delete_tag.
- Display preferences (not financial data - see below): set_dark_mode,
  set_privacy_mode, set_page_size, reorder_banks.

Rules:
- Always use a tool to answer questions about the user's actual data -
  never guess or make up numbers, ids, or tag names.
- When the user gives an amount, copy its digits EXACTLY as written -
  never round, transpose, or "autocorrect" it, especially when several
  items are listed in one message (e.g. "59rs => dahi and milk, 40rs =>
  haar"). Re-read the exact number next to each item before proposing it.
  If the user corrects an amount or any other detail you just proposed
  (e.g. "it's 59, not 58"), the very next proposal MUST use their
  corrected value exactly - never repeat the value they just corrected.
- To act on a specific expense or entry (delete/edit it), call
  list_recent_expenses or search_expenses FIRST to find the real
  expense_id/entry_id - never invent one.
- To move/transfer/send money from one of the user's banks to another,
  ALWAYS use transfer_money - never simulate a transfer with two separate
  create_expense calls (one debit, one topup). transfer_money handles
  both sides of the transfer as a single confirmed action.
- To delete many entries at once by tag, ALWAYS use
  bulk_delete_expenses_by_tag in one call - never loop
  delete_expense_entry yourself for a "delete all X" style request.
- Most of the tools above (everything except the lookup tools and the
  four display-preference tools) PAUSE for the user's explicit approval
  the first time you call them - you will not get a normal text result
  back then, the conversation simply stops until they answer. Only call
  one of these tools ONCE per user request; never call it a second time
  to "ask again" - the pause IS the confirmation request, you don't need
  to add your own question about it.
- NEVER call more than one pausing tool in the same turn/message, even
  for requests that sound like they need two actions (e.g. "add 100 to A
  and 200 to B", or "rename this tag and delete that one") - the approval
  pause only works correctly for one pending action at a time. Propose
  and get approval for the first action, and only once its result comes
  back, propose the second one in a follow-up turn.
- The display-preference tools (set_dark_mode, set_privacy_mode,
  set_page_size, reorder_banks) do NOT pause - they apply immediately and
  return a normal result right away, since they're just UI settings.
- The tool call you make AFTER the user has approved runs for real and
  returns a result like "Added successfully (expense id=...)", "Deleted
  successfully", "Entry updated.", or "Cancelled - the user did not
  approve this action." When you see one of those results, report it in
  PAST TENSE as something that already happened ("Done - I've added ₹150
  for Zomato lunch to Chase.") or, if cancelled, say plainly that you did
  not make the change. Never ask "would you like to confirm?" again at
  that point - it has already been decided.
""".strip()


def _system_prompt() -> str:
    """SYSTEM_PROMPT with today's actual date filled in, computed fresh on
    every call (never cached) - the model has no other way to know the
    real current date, and without this it was falling back to guessing
    from its training cutoff. That's what caused a genuinely past date
    ("8th October 2026" when today was the 30th) to be refused as a
    "future" date: the model simply didn't know what day it was."""
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    return SYSTEM_PROMPT.format(today=today)


# Shared across every request/user - see module docstring on why bare
# thread_id isn't used as the key directly.
_checkpointer = InMemorySaver()


def _scoped_thread_id(user_id: str, thread_id: str) -> str:
    return f"{user_id}:{thread_id}"


def _friendly_error(e: Exception) -> str:
    """Map a raised exception to a short, human-readable message - the raw
    exception (Groq error JSON, stack traces, etc.) is logged server-side
    for debugging but never shown to the user."""
    status = getattr(e, "status_code", None)
    name = type(e).__name__
    text = str(e).lower()

    # Recorded regardless of which branch below matches - surfaced on the
    # admin dashboard's usage panel (see app/core/llm_status.py) so "why is
    # chat slow/erroring" is visible without reading server logs.
    from app.core.llm import current_provider
    from app.core.llm_status import record_llm_error

    record_llm_error(current_provider(), e)

    if status == 429 or "ratelimit" in name.lower() or "rate_limit" in text:
        return (
            "Sorry, I'm a bit overloaded right now - the AI service has "
            "hit its usage limit for the moment. Please try again in a "
            "little while."
        )
    if status in (401, 403) or "authenticationerror" in name.lower():
        return "Sorry, I can't reach the AI service right now - please let the admin know."
    if status == 503 or "timeout" in name.lower() or "connectionerror" in name.lower():
        return "Sorry, the AI service is taking too long to respond. Please try again in a moment."
    return "Sorry, something went wrong. Please try again in a moment."


def _record_turn_token_usage(prior_message_count: int, result: dict, category: str | None) -> None:
    """Sums usage_metadata off only the messages THIS turn added, not the
    whole thread. The checkpointer makes graph.ainvoke() return the full
    cumulative message history every time (verified directly - a second
    turn on the same thread_id comes back with every earlier turn's
    messages still in result["messages"]), so naively summing all of
    them here would re-count every prior turn's tokens on every single
    subsequent turn. Slicing off everything before `prior_message_count`
    (the length captured right before this turn's ainvoke call) is what
    isolates just the new messages."""
    from app.core.llm import current_model, current_provider
    from app.core.llm_metrics import record_request

    new_messages = result.get("messages", [])[prior_message_count:]
    input_tokens = 0
    output_tokens = 0
    for m in new_messages:
        usage = getattr(m, "usage_metadata", None)
        if usage:
            input_tokens += usage.get("input_tokens", 0) or 0
            output_tokens += usage.get("output_tokens", 0) or 0
    if input_tokens or output_tokens:
        record_request(current_provider(), current_model(), input_tokens, output_tokens, category)


async def _extract_response(result: dict) -> dict:
    from app.core.llm_status import record_llm_success

    record_llm_success()
    interrupts = result.get("__interrupt__")
    if interrupts:
        if len(interrupts) > 1:
            # The model proposed more than one write action in the same
            # turn. A single Command(resume=...) can only route to one of
            # several interrupts paused in the same step, so resuming here
            # would silently confirm one action and leave the other stuck
            # (the exact "only one leg of the transfer happened" bug) -
            # refuse instead of guessing which one to resume.
            return {
                "answer": (
                    "I tried to propose more than one action at once, "
                    "which isn't safe to confirm - please try asking for "
                    "one action at a time."
                ),
                "pending_confirmation": False,
            }
        proposal = interrupts[0].value
        summary = proposal.get("summary", "Please confirm this action.")
        # Advisory only (see jev_insights.score_write_risk) - never blocks
        # the action, just decorates the confirm bubble with a warning
        # when Jev is configured and thinks this looks unusually large/
        # destructive. None (Jev unavailable/unsure) means no badge.
        risk = await score_write_risk(summary)
        return {
            "answer": summary,
            "pending_confirmation": True,
            "risk": risk,
        }
    messages = result.get("messages", [])
    answer = messages[-1].content if messages else "Sorry, I couldn't process that."
    return {"answer": answer, "pending_confirmation": False, "risk": None}


class AgentChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _build_graph(self, user_id: str, tool_category: str | None = None, export_box: dict | None = None):
        # Rebuilt per call so tools are always bound to *this* request's db
        # session - only the checkpointer (conversation memory) persists
        # across requests/calls. The LLM client itself is cached inside
        # get_llm() (app/core/llm.py), so this isn't reconstructing a
        # network client every turn - just picking up whatever's currently
        # cached there (or rebuilding it, the first call after an admin
        # changes the provider).
        tools = build_tools(user_id, self.db, export_box=export_box)
        if tool_category and tool_category in _TOOL_CATEGORIES:
            allowed = _ALWAYS_INCLUDED_TOOLS | _TOOL_CATEGORIES[tool_category]
            tools = [t for t in tools if t.name in allowed]
        llm = await get_llm(self.db)
        return create_agent(llm, tools, system_prompt=_system_prompt(), checkpointer=_checkpointer)

    async def _try_fast_path(self, user_id: str, question: str) -> dict | None:
        """Handles a small set of simple, parameter-free commands (display
        preference toggles, plain bank/tag listings) directly via Jev
        classification - zero Groq tokens spent, no agent/LLM call at
        all. Returns None when the message doesn't confidently match one
        of these (see jev_insights.classify_fast_path), and the caller
        should fall through to the normal ask() flow below.

        Deliberately bypasses the checkpointer entirely - these aren't
        part of any multi-turn flow worth remembering (nothing here ever
        needs a follow-up), so the small loss (the main agent won't later
        recall "did I turn on dark mode" if asked) is an acceptable
        trade for skipping Groq outright on these."""
        from app.services.app_settings_service import AppSettingsService

        flags = await AppSettingsService(self.db).get_feature_flags()
        if not flags.get("jev_fast_path_enabled", True):
            return None

        action = await classify_fast_path(question)
        if action is None:
            return None

        if action in ("dark_mode_on", "dark_mode_off", "privacy_mode_on", "privacy_mode_off"):
            pref_service = UserPreferenceService(self.db)
            is_on = action.endswith("_on")
            if action.startswith("dark_mode"):
                await pref_service.update_preferences(user_id, UserPreferenceUpdate(is_dark_mode=is_on))
                answer = f"Dark mode turned {'on' if is_on else 'off'}."
            else:
                await pref_service.update_preferences(user_id, UserPreferenceUpdate(privacy_mode_enabled=is_on))
                answer = f"Privacy mode turned {'on' if is_on else 'off'}."
            return {"answer": answer, "pending_confirmation": False, "risk": None}

        if action == "list_banks":
            banks = await BankService(self.db).get_banks(user_id)
            answer = (
                "\n".join(
                    f"- {b.name}: current balance ₹{b.current_balance:.2f}, "
                    f"total disbursed ₹{b.total_disbursed_till_now:.2f}"
                    for b in banks
                )
                if banks
                else "No bank accounts found."
            )
            return {"answer": answer, "pending_confirmation": False, "risk": None}

        if action == "list_tags":
            tags = await EntryTagService(self.db).get_tags(user_id)
            answer = "\n".join(f"- {t.name}" for t in tags) if tags else "No tags found."
            return {"answer": answer, "pending_confirmation": False, "risk": None}

        return None

    async def ask(self, user_id: str, thread_id: str, question: str) -> dict:
        fast_result = await self._try_fast_path(user_id, question)
        if fast_result is not None:
            return fast_result

        # Jev-based category routing (see agent_service module +
        # jev_insights.classify_chat_category) - purely a token-saving
        # optimization for the tool schemas sent this turn. Only applied
        # here, never in confirm() below: confirm() resumes a specific
        # already-paused tool call via the checkpointer, so it must always
        # see the full tool list that was present when that call paused,
        # or the resume could fail to find it.
        category = await classify_chat_category(question)
        export_box: dict = {}
        graph = await self._build_graph(user_id, tool_category=category, export_box=export_box)
        config = {"configurable": {"thread_id": _scoped_thread_id(user_id, thread_id)}}
        # Captured before invoking - see _record_turn_token_usage's
        # docstring on why this is needed (the checkpointer makes
        # ainvoke() return the FULL cumulative thread history, not just
        # this turn's new messages).
        prior_state = await graph.aget_state(config)
        prior_message_count = len(prior_state.values.get("messages", [])) if prior_state.values else 0
        try:
            result = await graph.ainvoke({"messages": [("user", question)]}, config=config)
        except Exception as e:
            logger.exception("Agent chat ask() failed")
            return {"answer": _friendly_error(e), "pending_confirmation": False, "risk": None}
        _record_turn_token_usage(prior_message_count, result, category)
        response = await _extract_response(result)
        if export_box:
            response["download"] = export_box
        return response

    async def confirm(self, user_id: str, thread_id: str, approve: bool) -> dict:
        # export_expenses never pauses for confirmation (it's read-only,
        # see tools.py), so confirm() never needs an export_box - this
        # resumes whatever write action was paused, not a fresh turn.
        graph = await self._build_graph(user_id)
        config = {"configurable": {"thread_id": _scoped_thread_id(user_id, thread_id)}}
        prior_state = await graph.aget_state(config)
        prior_message_count = len(prior_state.values.get("messages", [])) if prior_state.values else 0
        try:
            result = await graph.ainvoke(Command(resume="approve" if approve else "reject"), config=config)
        except Exception as e:
            logger.exception("Agent chat confirm() failed")
            return {"answer": _friendly_error(e), "pending_confirmation": False, "risk": None}
        _record_turn_token_usage(prior_message_count, result, category=None)
        return await _extract_response(result)
