"""One place that turns "these filters" into the rows of an expense report.

Used by BOTH the chatbot's export_expenses tool (download in the browser) and
the email worker (PDF attached to an email), so the two can never filter
differently. Pure data in, rows out: no file building here (see export.py).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import AdvancedSearchParams
from app.services.agent.export import build_export
from app.services.bank_service import BankService
from app.services.entry_tag_service import EntryTagService
from app.services.expense_service import ExpenseService


class ReportError(Exception):
    """Nothing to report / unknown account or tag. The message is safe to show the user."""


@dataclass
class ReportData:
    rows: list[dict]
    matched_count: int
    title: str


FILTER_KEYS = ("keyword", "tag_name", "bank_name", "start_date", "end_date", "min_amount", "max_amount", "top_n")


async def gather_export_rows(db: AsyncSession, user_id: str, filters: dict) -> ReportData:
    """`filters` uses the same names as the export_expenses tool (all optional,
    combined with AND; dates DD/MM/YYYY). Raises ReportError."""
    keyword = filters.get("keyword")
    tag_name = filters.get("tag_name")
    bank_name = filters.get("bank_name")
    start_date = filters.get("start_date")
    end_date = filters.get("end_date")
    min_amount = filters.get("min_amount")
    max_amount = filters.get("max_amount")
    top_n = filters.get("top_n")

    bank_service = BankService(db)
    tag_service = EntryTagService(db)
    expense_service = ExpenseService(db)

    bank_id = None
    if bank_name:
        banks = await bank_service.get_banks(user_id, name=bank_name)
        bank_id = banks[0].id if banks else None
        if bank_id is None:
            raise ReportError(f"No bank account named '{bank_name}' found. Try list_banks.")
    tag_id = None
    if tag_name:
        for t in await tag_service.get_tags(user_id):
            if t.name.lower() == tag_name.lower():
                tag_id = t.id
                break
        if tag_id is None:
            raise ReportError(f"No tag named '{tag_name}' found. Try list_tags.")

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
            search_kwargs["search_by_daterange"] = {"start_date": start_date, "end_date": end_date}
    elif bank_id:
        search_kwargs["bank_id"] = bank_id

    found_expenses, _total, _, _ = await expense_service.get_expenses(user_id, AdvancedSearchParams(**search_kwargs))

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
        raise ReportError("No matching expenses to export.")

    matched_count = len(rows)
    if top_n is not None and top_n > 0:
        # Most recent N, not highest-amount N - "top N" means recency to the
        # user (today first, then yesterday, then earlier).
        rows.sort(key=lambda r: datetime.strptime(r["date"], "%d/%m/%Y"), reverse=True)
        rows = rows[:top_n]

    title_bits_str = ", ".join(b for b in [tag_name, bank_name, keyword] if b)
    if top_n is not None:
        title = f"Top {len(rows)} Expenses" + (f" - {title_bits_str}" if title_bits_str else "")
    else:
        title = ("Expenses - " + title_bits_str) if title_bits_str else "Expenses"
    return ReportData(rows=rows, matched_count=matched_count, title=title)


def describe_range(filters: dict) -> str:
    start, end = filters.get("start_date"), filters.get("end_date")
    if start and end:
        return f"{start} to {end}"
    if start:
        return f"from {start}"
    return "all dates"


def build_report_file(data: ReportData, fmt: str) -> tuple[bytes, str, str]:
    """(bytes, filename, mime) for the rows, as pdf or csv."""
    return build_export(data.rows, data.title, "csv" if fmt == "csv" else "pdf")
