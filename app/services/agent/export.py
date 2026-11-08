"""CSV/PDF generation for the chat agent's export_expenses tool (see
tools.py). Pure functions, no DB/service dependency - they just turn
already-fetched rows into file bytes, so they're trivial to test and
reuse elsewhere if a non-chat export is ever added."""

import csv
import io
import os
from collections import OrderedDict
from datetime import datetime
from typing import Literal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# reportlab's built-in fonts (Helvetica et al.) don't include ₹ (U+20B9) -
# it rendered as a solid black "tofu" box instead of the rupee sign. DejaVu
# Sans does, and is bundled here (app/services/agent/fonts/) rather than
# relied on as a system font: the production image is python:3.11-slim,
# which has no fonts installed at all, so a path like
# /usr/share/fonts/... (present on this dev machine) would silently break
# in Docker. Registered once at import time.
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
pdfmetrics.registerFont(TTFont(FONT_REGULAR, os.path.join(_FONTS_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(_FONTS_DIR, "DejaVuSans-Bold.ttf")))

ExportRow = dict  # {"date": str, "bank": str, "description": str, "amount": float}

CSV_HEADERS = ["Date", "Bank", "Description", "Amount (₹)"]
PDF_GROUP_HEADERS = ["Date", "Description", "Amount (₹)"]  # no Bank column - it's the section heading


def _group_by_bank(rows: list[ExportRow]) -> "OrderedDict[str, list[ExportRow]]":
    """Preserves each bank's first-appearance order, not alphabetical -
    reads more naturally in a report than an arbitrary sort would."""
    groups: OrderedDict[str, list[ExportRow]] = OrderedDict()
    for r in rows:
        groups.setdefault(r["bank"], []).append(r)
    return groups


def _by_recency(rows: list[ExportRow]) -> list[ExportRow]:
    """Most recent date first (today, then yesterday, then everything
    else) - "sorted"/"top N" means recency here, not amount. `date` is
    DD/MM/YYYY; parsed so this orders correctly across month/year
    boundaries, not as a plain string sort."""
    return sorted(rows, key=lambda r: datetime.strptime(r["date"], "%d/%m/%Y"), reverse=True)


def _format_amount(amount: float, currency: str = "") -> str:
    """A top-up is money coming IN - showing it with a leading "-" (its
    raw stored sign; see CLAUDE.md's data model) read as a loss, not a
    credit. Shown with "+" and its magnitude instead; an expense keeps
    its plain unsigned amount, same as before."""
    if amount < 0:
        return f"+{currency}{abs(amount):,.2f}"
    return f"{currency}{amount:,.2f}"


def build_csv_bytes(rows: list[ExportRow]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADERS)
    for r in rows:
        writer.writerow([r["date"], r["bank"], r["description"], _format_amount(r["amount"])])
    return buf.getvalue().encode("utf-8")


def _totals_breakdown(rows: list[ExportRow]) -> list[tuple[str, float]]:
    """Expense total (positive amounts) and top-up total (negative
    amounts - see CLAUDE.md's data model: positive = debit/expense,
    negative = credit/top-up) kept SEPARATE, never netted into one
    combined figure - a single big top-up can otherwise make an
    otherwise-ordinary expense total look like a large negative number,
    which is what was actually confusing here. Only includes the types
    actually present, so a rows list with no top-ups still gets a plain
    single "Expense Total" (or "Top-up Total"), not two rows with one
    forced to zero."""
    expenses = [r["amount"] for r in rows if r["amount"] > 0]
    topups = [r["amount"] for r in rows if r["amount"] < 0]
    parts = []
    if expenses:
        parts.append(("Expense Total", sum(expenses)))
    if topups:
        parts.append(("Top-up Total", sum(topups)))
    return parts


def _summary_line(count_label: str, rows: list[ExportRow]) -> str:
    parts = _totals_breakdown(rows)
    if len(parts) <= 1:
        total = parts[0][1] if parts else 0.0
        return f"{len(rows)} {count_label} - total {_format_amount(total, '₹')}"
    breakdown = ", ".join(f"{label.lower()} {_format_amount(amt, '₹')}" for label, amt in parts)
    return f"{len(rows)} {count_label} - {breakdown}"


def _merge_date_column(table_data) -> list[tuple[int, int]]:
    """Data rows are always sorted by recency (_by_recency), so entries
    sharing a date are already consecutive - this finds those runs,
    blanks out the repeated date text in every row but the first (same
    reasoning as the Total rows: a SPAN cell only shows its top-left
    member's content), and returns the (start_row, end_row) ranges
    (table_data row indices, header included as row 0) to SPAN so the
    date visually merges into one cell instead of repeating."""
    spans = []
    n = len(table_data)
    start = 1  # row 0 is the header
    for i in range(2, n + 1):
        same = i < n and table_data[i][0] == table_data[start][0]
        if not same:
            if i - 1 > start:
                spans.append((start, i - 1))
                for r in range(start + 1, i):
                    table_data[r][0] = ""
            start = i
    return spans


def _styled_table(table_data, col_widths, totals: list[tuple[str, float]] | None = None) -> Table:
    """`totals`, when given, appends one bold row per (label, amount) at
    the very bottom - every table this builds gets this, not just the
    summary line above the table. Expense/top-up stay as separate rows
    (see _totals_breakdown) rather than one netted "Total" row."""
    n_cols = len(table_data[0])
    date_spans = _merge_date_column(table_data)
    style = [("SPAN", (0, start), (0, end)) for start, end in date_spans] + [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1f35")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Date column overrides the MIDDLE default above - a merged
        # multi-row date cell should read like a label sitting beside the
        # first row it covers, not float centered across the whole group.
        ("VALIGN", (0, 1), (0, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, (label, amount) in enumerate(totals or []):
        # A SPAN cell displays the content of its top-left member only -
        # the label has to live in column 0, not wherever it'll visually
        # end up, or it silently renders blank (confirmed - it did).
        total_row = [label] + [""] * (n_cols - 2) + [_format_amount(amount, "₹")]
        table_data = table_data + [total_row]
        last = len(table_data) - 1
        style += [
            ("SPAN", (0, last), (n_cols - 2, last)),
            ("FONTNAME", (0, last), (-1, last), FONT_BOLD),
            ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#e4e8f4")),
            # Only the first total row gets the separator line above it -
            # it's what visually detaches the totals from the data rows.
            *([("LINEABOVE", (0, last), (-1, last), 1, colors.HexColor("#1a1f35"))] if i == 0 else []),
        ]
    table = Table(table_data, repeatRows=1, colWidths=col_widths)
    # Table defaults to CENTER alignment within the frame (unlike
    # Paragraph, which hugs the left margin) - whenever the table's
    # computed width came out narrower than the page's content width
    # (common here, since one column's width is left as None/auto), it
    # visually drifted right of the title/summary text above it.
    table.hAlign = "LEFT"
    table.setStyle(TableStyle(style))
    return table


def build_pdf_bytes(rows: list[ExportRow], title: str) -> bytes:
    """One section per bank account, each with its own table and
    subtotal - not a single flat table. A tag (or any other filter) can
    span several of the user's banks, and lumping those together into
    one undifferentiated table made it hard to see which account each
    entry actually belonged to. Grand total still covers everything."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    # getSampleStyleSheet()'s defaults are all Helvetica - swap in the
    # Unicode-capable font registered above so ₹ renders in headings and
    # body text too, not just inside the table (see FONT_REGULAR comment).
    for style_name, font_name in (("Title", FONT_BOLD), ("Heading2", FONT_BOLD), ("Normal", FONT_REGULAR)):
        styles[style_name].fontName = font_name
    # getSampleStyleSheet()'s "Title" is center-aligned by default (TA_CENTER
    # = 1) - everything else on the page (summary line, tables) is
    # left-aligned, so the heading visually floated in its own column
    # instead of lining up with the content below it.
    styles["Title"].alignment = 0
    elements = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 10),
        Paragraph(_summary_line("entries", rows), styles["Normal"]),
        Spacer(1, 16),
    ]

    groups = _group_by_bank(rows)
    multi_bank = len(groups) > 1
    for bank_name, bank_rows in groups.items():
        # Most recent entry first within each bank's table, always - not
        # amount order. "Sorted"/"top N" means recency to the user
        # (today, then yesterday, then everything else), not biggest
        # amount - see _by_recency's docstring.
        bank_rows = _by_recency(bank_rows)
        totals = _totals_breakdown(bank_rows)
        if multi_bank:
            elements.append(Paragraph(bank_name, styles["Heading2"]))
            elements.append(Paragraph(_summary_line("entries", bank_rows), styles["Normal"]))
            elements.append(Spacer(1, 6))
            table_data = [PDF_GROUP_HEADERS] + [
                [r["date"], r["description"], _format_amount(r["amount"], "₹")] for r in bank_rows
            ]
            elements.append(_styled_table(table_data, [30 * mm, None, 34 * mm], totals=totals))
        else:
            # Single bank overall - the per-group heading/subtotal would
            # just repeat the grand total shown above, so skip straight
            # to one plain table instead (same shape export_expenses
            # always produced before grouping existed).
            table_data = [CSV_HEADERS] + [
                [r["date"], r["bank"], r["description"], _format_amount(r["amount"], "₹")] for r in bank_rows
            ]
            elements.append(_styled_table(table_data, [28 * mm, 28 * mm, None, 30 * mm], totals=totals))
        elements.append(Spacer(1, 18))

    doc.build(elements)
    return buf.getvalue()


def build_export(rows: list[ExportRow], title: str, fmt: Literal["csv", "pdf"]) -> tuple[bytes, str, str]:
    """Returns (content_bytes, filename, mime_type)."""
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip().replace(" ", "_")
    if fmt == "csv":
        return build_csv_bytes(rows), f"{safe_title}.csv", "text/csv"
    return build_pdf_bytes(rows, title), f"{safe_title}.pdf", "application/pdf"
