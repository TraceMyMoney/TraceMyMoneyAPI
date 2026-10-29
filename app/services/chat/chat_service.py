import re
import json
from datetime import date, datetime, timezone
from decimal import Decimal

import sqlglot
from sqlglot import exp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from langchain_core.output_parsers import StrOutputParser

from app.core.llm import LLM
from app.services.chat.prompts import (
    EXPENSE_SCHEMA,
    QUERY_GENERATION_PROMPT,
    RESPONSE_PROMPT,
)

MAX_ROWS = 20
STATEMENT_TIMEOUT_MS = 5000

# Tables this feature is allowed to query at all - enforced independently of
# (not instead of) the DB grants on smm_chat_readonly (PLAN.md Phase 4).
ALLOWED_TABLES = {
    "banks",
    "expenses",
    "expense_entries",
    "expense_entry_tags",
    "expense_entry_tag_links",
}


class ChatService:
    """
    Text-to-SQL chat with guardrails, per PLAN.md Phase 4:
      1. Runs only via the read-only `smm_chat_readonly` DB role (see
         app/db/postgres.py chat_engine), which has no write grants at all.
      2. Row-Level Security scopes every row to the current user via
         `SET LOCAL app.user_id` - the role is not the table owner, so RLS
         applies automatically.
      3. sqlglot parses the generated SQL and rejects anything but exactly
         one SELECT statement, referencing only the allowed tables.
      4. `SET LOCAL statement_timeout` bounds query runtime.
      5. Results are capped at MAX_ROWS.
      6. The whole query runs inside a transaction that is always rolled
         back, never committed - belt-and-suspenders, since the readonly
         role couldn't write even if the SQL weren't SELECT-only.
    """

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.llm = LLM

    async def ask(self, question: str, user_id: str) -> str:
        try:
            sql = await self._generate_sql(question)
            sql = self._validate_and_prepare(sql)
            data = await self._run(sql, user_id)
            return await self._format_response(question, data)

        except ValueError as e:
            return str(e)

        except Exception as e:
            return f"Sorry, I had trouble understanding that. Could you rephrase? ({str(e)})"

    async def _generate_sql(self, question: str) -> str:
        now = datetime.now(timezone.utc)

        chain = QUERY_GENERATION_PROMPT | self.llm | StrOutputParser()
        raw = await chain.ainvoke(
            {
                "schema": EXPENSE_SCHEMA,
                "today": now.strftime("%Y-%m-%d"),
                "month_start": now.replace(day=1).strftime("%Y-%m-%d"),
                "question": question,
            }
        )
        return self._clean_sql(raw)

    def _clean_sql(self, raw: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        cleaned = re.sub(r"^```(?:sql)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        return cleaned.rstrip(";").strip()

    def _validate_and_prepare(self, sql: str) -> str:
        """Parse + validate the LLM's SQL, raising ValueError on anything unsafe."""
        try:
            statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
        except Exception:
            raise ValueError("Sorry, I couldn't understand that question. Could you rephrase it?")

        if len(statements) != 1:
            raise ValueError("Sorry, that question needs a single query - could you simplify it?")

        stmt = statements[0]
        if not isinstance(stmt, exp.Select):
            raise ValueError("Sorry, I can only answer with read-only lookups.")

        tables = {t.name.lower() for t in stmt.find_all(exp.Table)}
        disallowed = tables - ALLOWED_TABLES
        if disallowed:
            raise ValueError("Sorry, I can't look up that information.")

        if not stmt.args.get("limit"):
            stmt = stmt.limit(MAX_ROWS)

        return stmt.sql(dialect="postgres")

    async def _run(self, sql: str, user_id: str) -> list:
        try:
            async with self.engine.connect() as conn:
                trans = await conn.begin()
                try:
                    await conn.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
                    await conn.execute(text("SET LOCAL app.user_id = :uid"), {"uid": user_id})
                    result = await conn.execute(text(sql))
                    rows = [dict(r) for r in result.mappings().all()[:MAX_ROWS]]
                    return self._serialize(rows)
                finally:
                    # Always roll back - this path never commits, even on
                    # success (guardrail #6 above).
                    await trans.rollback()
        except Exception:
            raise ValueError("Sorry, I couldn't process that query. Try rephrasing your question.")

    async def _format_response(self, question: str, data: list) -> str:
        chain = RESPONSE_PROMPT | self.llm | StrOutputParser()
        return await chain.ainvoke(
            {
                "question": question,
                "data": json.dumps(data) if data else "No data found",
            }
        )

    def _serialize(self, obj):
        """Convert DB-native types to JSON-serializable ones."""
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.strftime("%d %b %Y")
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize(i) for i in obj]
        return obj
