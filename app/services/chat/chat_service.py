import json
import re
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from langchain_core.output_parsers import StrOutputParser

from app.core.llm import LLM
from app.services.chat.prompts import (
    EXPENSE_SCHEMA,
    QUERY_GENERATION_PROMPT,
    RESPONSE_PROMPT,
)


class ChatService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.llm = LLM

    async def ask(self, question: str, user_id: str) -> str:
        try:
            pipeline = await self._generate_pipeline(question, user_id)
            pipeline = self._sanitize(pipeline, user_id)
            data = await self._run(pipeline)
            return await self._format_response(question, data)

        except ValueError as e:
            return str(e)

        except Exception as e:
            return f"Sorry, I had trouble understanding that. Could you rephrase? ({str(e)})"

    async def _generate_pipeline(self, question: str, user_id: str) -> list:
        now = datetime.utcnow()

        chain = QUERY_GENERATION_PROMPT | self.llm | StrOutputParser()
        raw = await chain.ainvoke(
            {
                "schema": EXPENSE_SCHEMA,
                "user_id": user_id,
                "today": now.strftime("%Y-%m-%dT00:00:00Z"),
                "month_start": now.replace(day=1).strftime("%Y-%m-%dT00:00:00Z"),
                "question": question,
            }
        )

        return self._parse_json(raw)

    def _sanitize(self, pipeline: list, user_id: str) -> list:
        pipeline_str = json.dumps(pipeline)
        pipeline_str = re.sub(
            r'ISODate\("([^"]+)"\)',
            lambda m: f'{{"$date": "{m.group(1)}"}}',
            pipeline_str,
        )
        pipeline = json.loads(pipeline_str)
        pipeline = self._resolve_dates(pipeline)
        pipeline = self._inject_user_id(pipeline, user_id)
        pipeline = self._ensure_user_filter(pipeline, user_id)

        return pipeline

    async def _run(self, pipeline: list) -> list:
        try:
            cursor = self.db.expense.aggregate(pipeline)
            results = await cursor.to_list(length=20)
            return self._serialize(results)
        except Exception as e:
            raise ValueError(f"Sorry, I couldn't process that query. Try rephrasing your question.")

    async def _format_response(self, question: str, data: list) -> str:
        chain = RESPONSE_PROMPT | self.llm | StrOutputParser()
        return await chain.ainvoke(
            {
                "question": question,
                "data": json.dumps(data) if data else "No data found",
            }
        )

    def _parse_json(self, raw: str) -> list:
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        clean = raw.strip()
        clean = re.sub(r"^```(?:json)?", "", clean).strip()
        clean = re.sub(r"```$", "", clean).strip()

        match = re.search(r"(\[.*\])", clean, re.DOTALL)
        if match:
            clean = match.group(1)

        try:
            result = json.loads(clean)
            if not isinstance(result, list):
                raise ValueError("Expected a JSON array")
            return result
        except json.JSONDecodeError:
            raise ValueError("Sorry, I couldn't understand that question. Could you rephrase it?")

    def _resolve_dates(self, obj):
        """Convert {"$date": "2026-03-23T00:00:00Z"} → Python datetime."""
        if isinstance(obj, dict):
            if "$date" in obj and len(obj) == 1:
                date_str = obj["$date"]
                try:
                    return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    return datetime.strptime(date_str[:10], "%Y-%m-%d")
            return {k: self._resolve_dates(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_dates(i) for i in obj]
        return obj

    def _inject_user_id(self, obj, user_id: str):
        """Replace string user_id with real ObjectId."""
        if isinstance(obj, dict):
            return {
                k: (
                    ObjectId(user_id)
                    if k == "user_id" and isinstance(v, str)
                    else self._inject_user_id(v, user_id)
                )
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [self._inject_user_id(i, user_id) for i in obj]
        return obj

    def _ensure_user_filter(self, pipeline: list, user_id: str) -> list:
        """Make sure first stage always filters by user_id."""
        if not pipeline:
            return pipeline
        first = pipeline[0]
        if "$match" in first:
            if "user_id" not in first["$match"]:
                first["$match"]["user_id"] = ObjectId(user_id)
        else:
            pipeline.insert(0, {"$match": {"user_id": ObjectId(user_id)}})
        return pipeline

    def _serialize(self, obj):
        """Convert ObjectId and datetime to JSON-serializable types."""
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.strftime("%d %b %Y")
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize(i) for i in obj]
        return obj
