"""Turn a forwarded bank / UPI SMS into a structured transaction.

Pure functions, no database or network. Indian bank SMS formats vary a lot,
so this is deliberately forgiving: it needs an amount and a debit/credit
word, and treats everything else (merchant, date, account digits) as
optional. Anything that is not clearly a transaction (OTPs, balance
alerts, promotions) returns None and is ignored by the caller.
"""

import re
from dataclasses import dataclass
from datetime import datetime

DEBIT_WORDS = ("debited", "spent", "sent", "paid", "withdrawn", "purchase", "debit")
CREDIT_WORDS = ("credited", "received", "deposited", "refund", "credit")

# Amount: "Rs.250", "Rs 1,500.50", "INR 40", "₹40".
_AMOUNT = re.compile(r"(?:rs\.?|inr|₹)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
# "debited by 40.0" style, where no currency symbol is given.
_BARE_AMOUNT = re.compile(r"(?:debited|credited)\s+(?:by|for|with)\s+([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
_BALANCE_CONTEXT = re.compile(r"(bal|balance|limit|avl|available|outstanding)\W*$", re.I)

_OTP = re.compile(r"\botp\b|one[\s-]?time password|verification code", re.I)

_MONTHS = {
    m: i
    for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)
}

_ACCOUNT = re.compile(
    r"(?:a/?c|acct|account|card)(?:\s+(?:no\.?|number|ending(?:\s+(?:with|in))?))?"
    r"\s*[:\-]?\s*[xX*•.]*\s*(\d{3,4})\b",
    re.I,
)

BANK_KEYWORDS = (
    "HDFC",
    "SBI",
    "ICICI",
    "AXIS",
    "KOTAK",
    "PNB",
    "BOB",
    "CANARA",
    "IDFC",
    "INDUSIND",
    "YES BANK",
    "FEDERAL",
    "UNION BANK",
    "BANK OF BARODA",
    "AMAZON PAY",
    "PAYTM",
    "PHONEPE",
    "GPAY",
)

_MERCHANT_STOP = r"(?=\s+(?:on|refno|ref|upi|via|using|txn|trf|dated|date|avl|bal|not|if)\b|[.\n,;(]|$)"
_DEBIT_MERCHANT = re.compile(r"\b(?:to|at)\s+(?:vpa\s+)?(.+?)" + _MERCHANT_STOP, re.I)
_CREDIT_FROM = re.compile(r"\bfrom\s+(?:vpa\s+)?(?!rs\b|inr\b|₹|\d)(.+?)" + _MERCHANT_STOP, re.I)
_CREDIT_BY = re.compile(r"\bby\s+(?:vpa\s+)?(?!rs\b|inr\b|₹|\d)(.+?)" + _MERCHANT_STOP, re.I)


@dataclass
class ParsedSms:
    amount: float
    txn_type: str  # "debit" | "credit"
    merchant: str | None = None
    txn_date: datetime | None = None  # midnight of the transaction day
    account_hint: str | None = None  # last 3-4 digits of the account / card
    bank_hint: str | None = None  # e.g. "HDFC"


def _clean_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def _find_amount(text: str) -> float | None:
    for m in _AMOUNT.finditer(text):
        before = text[max(0, m.start() - 16) : m.start()]
        if _BALANCE_CONTEXT.search(before):
            continue  # "Avl Bal Rs 1,234" is the balance, not the transaction
        return _clean_amount(m.group(1))
    m = _BARE_AMOUNT.search(text)
    return _clean_amount(m.group(1)) if m else None


def _find_type(text: str) -> str | None:
    low = text.lower()
    best: tuple[int, str] | None = None
    for words, kind in ((DEBIT_WORDS, "debit"), (CREDIT_WORDS, "credit")):
        for w in words:
            m = re.search(rf"\b{w}\b", low)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), kind)
    return best[1] if best else None


def _build_date(day: int, month: int, year: int) -> datetime | None:
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _find_date(text: str) -> datetime | None:
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        return _build_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"\b(\d{1,2})[ \-/]?([A-Za-z]{3})[a-z]*[ \-/]?(\d{2,4})\b", text)
    if m and m.group(2).lower() in _MONTHS:
        return _build_date(int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
    if m:
        return _build_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _clean_merchant(raw: str) -> str | None:
    name = re.sub(r"@[A-Za-z0-9.\-]+", "", raw)  # UPI handle: swiggy@icici -> swiggy
    name = re.sub(r"\s+", " ", name).strip(" .-:,*")
    if not name or re.match(r"(?:a/?c|acct|account|card)\b", name, re.I):
        return None
    if re.fullmatch(r"[\d\sxX*]+", name):  # a masked or numeric handle tells the user nothing
        return None
    if name.isupper():
        name = name.title()
    return name[:100]


def _find_merchant(text: str, txn_type: str) -> str | None:
    patterns = (_DEBIT_MERCHANT,) if txn_type == "debit" else (_CREDIT_FROM, _CREDIT_BY)
    for pattern in patterns:
        for m in pattern.finditer(text):
            merchant = _clean_merchant(m.group(1))
            if merchant:
                return merchant
    return None


def _find_bank_hint(text: str) -> str | None:
    up = text.upper()
    best: tuple[int, str] | None = None
    for kw in BANK_KEYWORDS:
        i = up.find(kw)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, kw)
    return best[1] if best else None


def parse_sms(text: str) -> ParsedSms | None:
    """Return the transaction described by `text`, or None if it isn't one."""
    if not text or _OTP.search(text):
        return None
    txn_type = _find_type(text)
    amount = _find_amount(text)
    if txn_type is None or amount is None or amount <= 0:
        return None

    account = _ACCOUNT.search(text)
    return ParsedSms(
        amount=amount,
        txn_type=txn_type,
        merchant=_find_merchant(text, txn_type),
        txn_date=_find_date(text),
        account_hint=account.group(1) if account else None,
        bank_hint=_find_bank_hint(text),
    )


def match_bank(text: str, bank_hint: str | None, banks: list[dict]) -> str | None:
    """Pick which of the user's accounts an SMS belongs to.

    `banks` is a list of {"id", "name"}. The longest account name found in the
    SMS wins (so "SBI Credit Card" beats "SBI"); failing that, a bank keyword
    like HDFC picks the single account whose name contains it. Returns the
    bank id, or None when it's ambiguous - the user then picks in the inbox.
    """
    up = text.upper()
    named = [b for b in banks if b["name"].strip() and b["name"].upper() in up]
    if named:
        return max(named, key=lambda b: len(b["name"]))["id"]
    if bank_hint:
        hinted = [b for b in banks if bank_hint in b["name"].upper()]
        if len(hinted) == 1:
            return hinted[0]["id"]
    return None
