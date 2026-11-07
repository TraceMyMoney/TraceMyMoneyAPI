"""
The four Jev-backed enhancements (see app/core/jev.py for the "what/why
this is optional" context). Every function here returns None on any
failure - including Jev being unconfigured, a network error, or an
unexpected response shape - so callers can treat "no enhancement" as the
normal, expected case and fall back to today's existing behavior.
"""

import logging
from typing import Optional

from app.core.jev import get_classifier

logger = logging.getLogger(__name__)


async def suggest_tag(description: str, tag_names: list[str]) -> Optional[dict]:
    """Suggest which of the user's existing tags best fits a new expense
    description. Returns {"tag_name": str, "confidence": float} or None."""
    classifier = get_classifier()
    if classifier is None or not tag_names or not description.strip():
        return None
    try:
        from langchain_typesafe import Choice

        response = await classifier.ainvoke(
            {
                "state": description,
                "questions": {
                    "tag": Choice(
                        instructions=(
                            "Which existing tag best fits this personal expense "
                            "description? Pick the single best match."
                        ),
                        criteria={name: None for name in tag_names},
                    ),
                },
            }
        )
        result = response.choices["tag"]
        return {"tag_name": result.choice, "confidence": result.confidence}
    except Exception:
        logger.exception("Jev tag suggestion failed")
        return None


# Chat tool categories - must match the groupings in
# app/services/agent/agent_service.py's _TOOL_CATEGORIES.
CHAT_CATEGORIES = {
    "read": "A question about existing data - balances, spending, listing banks/tags/expenses, searching.",
    "expense": "Adding, editing, or deleting an expense or a single entry within one (not a transfer).",
    "transfer": "Moving money between two of the user's own bank accounts.",
    "bank": "Creating, renaming, deleting a bank account, or correcting its balance.",
    "tag": "Creating, renaming, or deleting an expense tag.",
    "preference": "Changing a display setting - dark mode, privacy mode, page size, bank display order.",
    "other": "Anything that doesn't clearly fit the categories above, or a mix of several.",
}

# Below this confidence, callers should fall back to including every tool
# rather than trust a shaky classification - a wrong category would make
# the agent unable to complete a request it could otherwise handle today.
CHAT_CATEGORY_CONFIDENCE_FLOOR = 0.6


async def classify_chat_category(question: str) -> Optional[str]:
    """Classify a user's chat message into one of CHAT_CATEGORIES, to let
    the caller load a smaller tool subset for this turn (cuts token
    overhead - see PLAN.md/session notes on the rate-limit issues this is
    meant to help with). Returns the category name, or None if Jev is
    unavailable, failed, or wasn't confident enough to trust - callers
    must treat None the same as "other" (include every tool)."""
    classifier = get_classifier()
    if classifier is None or not question.strip():
        return None
    try:
        from langchain_typesafe import Choice

        response = await classifier.ainvoke(
            {
                "state": question,
                "questions": {
                    "category": Choice(
                        instructions="Which category does this chat message fall into?",
                        criteria=CHAT_CATEGORIES,
                    ),
                },
            }
        )
        result = response.choices["category"]
        if result.confidence is not None and result.confidence < CHAT_CATEGORY_CONFIDENCE_FLOOR:
            return None
        return result.choice
    except Exception:
        logger.exception("Jev chat category classification failed")
        return None


# Simple, parameter-free commands that can be handled without ever
# calling the main chat LLM - see AgentChatService._try_fast_path. Keep
# this to actions with NO meaningful arguments to extract (a bare on/off
# toggle or a no-filter listing); anything needing argument extraction
# (page size, bank names, filters, deletions, etc.) stays on the normal
# Groq-backed path, since Jev's bounded choice/score/noul types aren't
# suited to pulling arbitrary values out of free text.
_FAST_PATH_ACTIONS = {
    "dark_mode_on": "Turn dark mode ON.",
    "dark_mode_off": "Turn dark mode OFF (light mode).",
    "privacy_mode_on": "Turn privacy/hide-amounts mode ON.",
    "privacy_mode_off": "Turn privacy/hide-amounts mode OFF (show amounts).",
    "list_banks": "List all bank accounts and their balances - nothing else asked.",
    "list_tags": "List all expense tags - nothing else asked.",
    "other": (
        "Anything else - needs real expense/spending data, reasoning, "
        "multiple steps, specific amounts/names/dates, or free-form "
        "conversation."
    ),
}
# Higher bar than CHAT_CATEGORY_CONFIDENCE_FLOOR - a wrong guess here
# skips the real agent/LLM entirely, so false positives are more costly
# than for the (recoverable) tool-subset routing above.
FAST_PATH_CONFIDENCE_FLOOR = 0.8

# Deterministic safety net, checked BEFORE ever asking Jev: none of the
# 6 fast-path actions involve creating, deleting, or modifying anything
# beyond a bare on/off toggle, so any message containing one of these
# words should never take the fast path, full stop - regardless of what
# the classifier says. This exists because a classifier got this wrong in
# practice once (with a different provider): "delete all banks" /
# "destroy all banks" were both confidently (mis)classified as list_banks
# and silently answered with a bank listing instead of being treated as a
# destructive request. A single ML classifier is not something to trust
# unchecked for a safety-relevant routing decision - false negatives here
# just mean a slower (but correct) trip through the real agent; false
# positives mean a destructive request gets silently ignored, which is
# far worse.
_FAST_PATH_BLOCKED_WORDS = (
    "delete",
    "destroy",
    "remove",
    "erase",
    "wipe",
    "clear",
    "drop",
    "kill",
    "cancel",
    "close",
    "disable",
    "deactivate",
    "create",
    "add",
    "rename",
    "transfer",
    "edit",
    "modify",
    "update",
    "correct",
    "change",
    "move",
    "send",
)


async def classify_fast_path(question: str) -> Optional[str]:
    """Classify whether a chat message is one of the narrow _FAST_PATH_ACTIONS
    with high enough confidence to answer without the main LLM at all.
    Returns the action name, or None (treat as "not a fast path, use the
    normal flow") when unavailable, unsure, or the message doesn't fit."""
    classifier = get_classifier()
    if classifier is None or not question.strip():
        return None
    lowered = question.lower()
    if any(word in lowered for word in _FAST_PATH_BLOCKED_WORDS):
        return None
    try:
        from langchain_typesafe import Choice

        response = await classifier.ainvoke(
            {
                "state": question,
                "questions": {
                    "action": Choice(
                        instructions=(
                            "Which single action does this message request? "
                            "Pick 'other' unless it is EXACTLY and ONLY one "
                            "of the other listed simple actions, with "
                            "nothing else being asked."
                        ),
                        criteria=_FAST_PATH_ACTIONS,
                    ),
                },
            }
        )
        result = response.choices["action"]
        if result.choice == "other" or result.confidence is None or result.confidence < FAST_PATH_CONFIDENCE_FLOOR:
            return None
        return result.choice
    except Exception:
        logger.exception("Jev fast-path classification failed")
        return None


async def score_write_risk(summary: str) -> Optional[dict]:
    """Score how risky/unusual a proposed write action looks, to show a
    warning badge on its confirmation bubble. Returns
    {"flagged": bool, "probability": float} (probability of "risky") or
    None - never blocks the action itself, this only decorates the
    existing confirm UI; the interrupt/confirm flow stays the sole
    enforcement mechanism."""
    classifier = get_classifier()
    if classifier is None or not summary.strip():
        return None
    try:
        from langchain_typesafe import Noul

        response = await classifier.ainvoke(
            {
                "state": summary,
                "questions": {
                    "risky": Noul(
                        instructions=(
                            "Is this proposed personal-finance action unusually "
                            "large, destructive, or worth a second look before "
                            "approving (e.g. a large transfer, a bulk delete, a "
                            "balance correction, or deleting a bank account)?"
                        )
                    ),
                },
            }
        )
        probability = response.nouls["risky"].noul
        return {"flagged": probability >= 0.6, "probability": probability}
    except Exception:
        logger.exception("Jev risk scoring failed")
        return None
