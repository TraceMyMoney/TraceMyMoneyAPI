from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    """A new question, OR a response to a pending confirmation (set
    `confirm` instead of `question` in that case - the agent remembers
    what it proposed via `thread_id`)."""

    thread_id: str
    question: Optional[str] = None
    confirm: Optional[bool] = None


class ChatRisk(BaseModel):
    """Jev's (TypeSafe AI) advisory read on how risky a proposed action
    looks - see app/services/jev_insights.score_write_risk. Purely a UI
    hint; never blocks anything."""

    flagged: bool
    probability: float


class ChatResponse(BaseModel):
    answer: str
    # True when `answer` is a proposed action awaiting the user's
    # approval - the frontend should show Confirm/Cancel and send the
    # decision back as {thread_id, confirm: true|false}.
    pending_confirmation: bool = False
    # Only ever set alongside pending_confirmation=True, and only when
    # Jev is configured/confident - null otherwise.
    risk: Optional[ChatRisk] = None
