"""
Optional integration with TypeSafe AI's Jev decision model - a fast,
non-generative classifier (bounded yes/no, multiple-choice, or
scale-rating answers with calibrated probabilities, not free text), used
here for a few narrow jobs that don't need a full LLM call: suggesting a
tag for a new expense, routing a chat turn to a smaller tool subset,
scoring how risky a proposed write action looks, and a handful of
Groq-bypassing fast-path commands (see app/services/jev_insights.py).

Previously pointed at an unaffiliated third-party service ("Laya Studio")
as a stopgap while TypeSafe billing credits were unavailable - reverted
back to TypeSafe's own API on request. See git history for that version
if it's ever needed again (same request shape, different response
parsing).

Entirely optional. `get_classifier()` returns None whenever
TYPESAFE_API_KEY isn't configured (or construction fails for any other
reason) - every caller in this codebase MUST treat None as "Jev is
unavailable right now" and skip the enhancement silently. Nothing else in
the app may ever hard-depend on this being available.
"""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_classifier = None
_attempted = False


def get_classifier():
    """Shared TypeSafeClassifier instance, or None if Jev isn't usable
    right now. Safe to call from anywhere; never raises."""
    global _classifier, _attempted
    if _attempted:
        return _classifier
    _attempted = True

    if not settings.TYPESAFE_API_KEY:
        return None

    try:
        from langchain_typesafe import TypeSafeClassifier

        _classifier = TypeSafeClassifier(api_key=settings.TYPESAFE_API_KEY)
    except Exception:
        logger.exception("Failed to construct the Jev classifier - disabling Jev features")
        _classifier = None
    return _classifier
