from pydantic import BaseModel


class ChatRequest(BaseModel):
    """A new question, OR a response to a pending confirmation (set
    `confirm` instead of `question` in that case - the agent remembers
    what it proposed via `thread_id`)."""

    thread_id: str
    question: str | None = None
    confirm: bool | None = None


class ChatRisk(BaseModel):
    """Jev's (TypeSafe AI) advisory read on how risky a proposed action
    looks - see app/services/jev_insights.score_write_risk. Purely a UI
    hint; never blocks anything."""

    flagged: bool
    probability: float


class ChatDownload(BaseModel):
    """A file the export_expenses tool generated this turn - base64-
    encoded so it travels inline in this same JSON response (exports are
    small, a few hundred rows at most - see tools.py's per_page=500 cap),
    no separate download endpoint or temp-file storage needed. The
    frontend decodes this and triggers a normal browser file-save."""

    filename: str
    mime_type: str
    content_b64: str


class ChatResponse(BaseModel):
    answer: str
    # True when `answer` is a proposed action awaiting the user's
    # approval - the frontend should show Confirm/Cancel and send the
    # decision back as {thread_id, confirm: true|false}.
    pending_confirmation: bool = False
    # Only ever set alongside pending_confirmation=True, and only when
    # Jev is configured/confident - null otherwise.
    risk: ChatRisk | None = None
    # Only set when this turn called export_expenses - see ChatDownload.
    download: ChatDownload | None = None
