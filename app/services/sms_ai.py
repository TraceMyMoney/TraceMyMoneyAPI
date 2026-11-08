"""Read a bank / UPI SMS with the admin-configured chat model.

The fixed patterns in sms_parser.py handle the common formats, but every
bank words things differently. This asks the same model the chat assistant
uses to pull the transaction out as structured data, so odd formats still
work. It never raises: any failure (no API key, rate limit, timeout, a
reply that doesn't check out) returns None and the caller falls back to
the fixed patterns.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.sms_parser import ParsedSms

logger = logging.getLogger(__name__)

AI_TIMEOUT_SECONDS = 12  # an iPhone Shortcut is waiting on this response
# The answer is a handful of fields. Passing this per call keeps the admin's
# global max-tokens setting (which can exceed a model's limit, and made Groq
# reject the request) out of the SMS path entirely.
MAX_OUTPUT_TOKENS = 400

SYSTEM_PROMPT = """You extract ONE bank or UPI transaction from an Indian bank SMS.

Rules:
- is_transaction is false for OTPs, balance or limit alerts, offers, reminders, and anything that is not a completed debit or credit.
- type is "debit" when money left the account (debited, spent, sent, paid, withdrawn) and "credit" when money came in (credited, received, refund).
- amount is the transaction amount in rupees as a plain number. Never use the available balance or limit.
- merchant is the person or business that was paid (debit) or that paid the user (credit). Remove reference numbers, UPI handles and account digits. Use Title Case.
- date is the transaction date as YYYY-MM-DD. A value like 06Nov26 means 6 November 2026. Use null if the SMS has no date.
- account_last_digits are the last 3 or 4 digits of the account or card, digits only.
- bank is the short bank name in capitals if the SMS names one (SBI, HDFC, ICICI...), otherwise null.
Never invent a value. Use null when you are not sure."""


class SmsExtraction(BaseModel):
    is_transaction: bool = Field(description="True only for a completed debit or credit")
    type: Literal["debit", "credit"] | None = None
    amount: float | None = None
    merchant: str | None = None
    date: str | None = Field(default=None, description="YYYY-MM-DD")
    account_last_digits: str | None = None
    bank: str | None = None


class AiVerdict(BaseModel):
    """What the model decided: either a parsed transaction or "not a transaction"."""

    parsed: ParsedSms | None = None  # None means the model said this is not a transaction

    model_config = {"arbitrary_types_allowed": True}


def _numbers_in(text: str) -> list[float]:
    out = []
    for raw in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def _to_parsed(data: SmsExtraction, text: str) -> ParsedSms | None:
    """Turn the model's answer into a ParsedSms, or None if it doesn't check out."""
    if data.type not in ("debit", "credit") or data.amount is None or data.amount <= 0:
        return None
    # Guard against a made-up amount: it has to literally appear in the SMS.
    if not any(abs(n - data.amount) < 0.005 for n in _numbers_in(text)):
        logger.warning("AI amount %s not found in SMS; ignoring AI result", data.amount)
        return None

    txn_date = None
    if data.date:
        try:
            txn_date = datetime.strptime(data.date, "%Y-%m-%d")
        except ValueError:
            txn_date = None

    digits = re.sub(r"\D", "", data.account_last_digits or "")[-4:] or None
    merchant = re.sub(r"\s+", " ", data.merchant or "").strip()[:100] or None
    bank = (data.bank or "").strip().upper() or None
    return ParsedSms(
        amount=float(data.amount),
        txn_type=data.type,
        merchant=merchant,
        txn_date=txn_date,
        account_hint=digits,
        bank_hint=bank,
    )


async def extract_with_ai(db, text: str, received_on: str) -> AiVerdict | None:
    """Ask the model. Returns an AiVerdict, or None when the AI couldn't be used."""
    if not settings.SMS_AI_PARSING:
        return None
    try:
        from app.core.llm import current_provider, get_llm
        from app.core.llm_status import record_llm_error, record_llm_success

        llm = await get_llm(db)
        structured = llm.with_structured_output(SmsExtraction)
        try:
            data = await asyncio.wait_for(
                structured.ainvoke(
                    [
                        ("system", SYSTEM_PROMPT),
                        ("human", f"Message received on {received_on}:\n{text}"),
                    ],
                    max_tokens=MAX_OUTPUT_TOKENS,
                ),
                timeout=AI_TIMEOUT_SECONDS,
            )
        except Exception as e:  # rate limit, timeout, bad key...
            record_llm_error(current_provider(), e)
            raise
        record_llm_success()
    except Exception:
        logger.exception("AI SMS parsing failed; using the fixed patterns")
        return None

    if not isinstance(data, SmsExtraction):
        return None
    if not data.is_transaction:
        return AiVerdict(parsed=None)
    parsed = _to_parsed(data, text)
    return AiVerdict(parsed=parsed) if parsed else None
