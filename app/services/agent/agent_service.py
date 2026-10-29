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

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLM
from app.services.agent.tools import build_tools

SYSTEM_PROMPT = """
You are the in-app assistant for "Stalk My Money", a personal expense
tracker. Be warm, concise, and conversational - 2-4 sentences unless the
user asks for a list. Always show money as ₹ (Indian Rupees).

You have tools to look up the user's banks, tags, and expenses, and to
propose adding an expense/topup, deleting an expense, or creating a tag.

Rules:
- Always use a tool to answer questions about the user's actual data -
  never guess or make up numbers.
- To delete an expense, call list_recent_expenses first to find the
  correct id - never invent one.
- create_expense, delete_expense, and create_tag PAUSE for the user's
  explicit approval the first time you call them - you will not get a
  normal text result back then, the conversation simply stops until they
  answer. Only call one of these tools ONCE per user request; never call
  it a second time to "ask again" - the pause IS the confirmation request,
  you don't need to add your own question about it.
- The tool call you make AFTER the user has approved runs for real and
  returns a result like "Added successfully (expense id=...)" or "Deleted
  successfully" or "Cancelled - the user did not approve this action."
  When you see one of those results, report it in PAST TENSE as something
  that already happened ("Done - I've added ₹150 for Zomato lunch to
  Chase.") or, if cancelled, say plainly that you did not make the change.
  Never ask "would you like to confirm?" again at that point - it has
  already been decided.
""".strip()

# Shared across every request/user - see module docstring on why bare
# thread_id isn't used as the key directly.
_checkpointer = InMemorySaver()


def _scoped_thread_id(user_id: str, thread_id: str) -> str:
    return f"{user_id}:{thread_id}"


def _extract_response(result: dict) -> dict:
    interrupts = result.get("__interrupt__")
    if interrupts:
        proposal = interrupts[0].value
        return {
            "answer": proposal.get("summary", "Please confirm this action."),
            "pending_confirmation": True,
        }
    messages = result.get("messages", [])
    answer = messages[-1].content if messages else "Sorry, I couldn't process that."
    return {"answer": answer, "pending_confirmation": False}


class AgentChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _build_graph(self, user_id: str):
        # Rebuilt per call so tools are always bound to *this* request's db
        # session - only the checkpointer (conversation memory) persists
        # across requests/calls.
        tools = build_tools(user_id, self.db)
        return create_agent(
            LLM, tools, system_prompt=SYSTEM_PROMPT, checkpointer=_checkpointer
        )

    async def ask(self, user_id: str, thread_id: str, question: str) -> dict:
        graph = self._build_graph(user_id)
        config = {"configurable": {"thread_id": _scoped_thread_id(user_id, thread_id)}}
        try:
            result = await graph.ainvoke(
                {"messages": [("user", question)]}, config=config
            )
        except Exception as e:
            return {
                "answer": f"Sorry, something went wrong. ({e})",
                "pending_confirmation": False,
            }
        return _extract_response(result)

    async def confirm(self, user_id: str, thread_id: str, approve: bool) -> dict:
        graph = self._build_graph(user_id)
        config = {"configurable": {"thread_id": _scoped_thread_id(user_id, thread_id)}}
        try:
            result = await graph.ainvoke(
                Command(resume="approve" if approve else "reject"), config=config
            )
        except Exception as e:
            return {
                "answer": f"Sorry, something went wrong. ({e})",
                "pending_confirmation": False,
            }
        return _extract_response(result)
