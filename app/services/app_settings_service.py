"""Generic admin-editable key/value settings (app/db/tables.py:app_settings),
used by the admin dashboard for things that need to change at runtime
without a redeploy: which chat-LLM provider/model is active, and feature
flags. See app/core/llm.py for how ai_config is consumed."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import app_settings

AI_CONFIG_KEY = "ai_config"
FEATURE_FLAGS_KEY = "feature_flags"
PROVIDER_KEYS_KEY = "provider_keys"

# Every provider build_llm() (app/core/llm.py) knows how to construct.
# Keeping this list here (not in llm.py) so the admin API can validate a
# PUT without importing the langchain client classes.
SUPPORTED_PROVIDERS = ("groq", "openai", "anthropic", "openrouter")

DEFAULT_AI_CONFIG = {
    "provider": "groq",
    "model": None,  # None -> llm.py falls back to settings.GROQ_MODEL_NAME
    "temperature": None,
    "max_tokens": None,
    "timeout": 20,
    "max_retries": 1,
}

DEFAULT_FEATURE_FLAGS = {
    "jev_fast_path_enabled": True,
    "voice_input_enabled": True,
}


class AppSettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_raw(self, key: str) -> Optional[dict]:
        result = await self.db.execute(select(app_settings).where(app_settings.c.key == key))
        row = result.mappings().first()
        return row["value"] if row else None

    async def set_raw(self, key: str, value: dict, updated_by: Optional[str] = None) -> dict:
        now = datetime.now(timezone.utc)
        stmt = pg_insert(app_settings).values(
            key=key,
            value=value,
            updated_at=now,
            updated_by=uuid.UUID(updated_by) if updated_by else None,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[app_settings.c.key],
            set_={
                "value": stmt.excluded.value,
                "updated_at": stmt.excluded.updated_at,
                "updated_by": stmt.excluded.updated_by,
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return value

    async def get_ai_config(self) -> dict:
        """The active LLM provider/model config, merged over the defaults
        so a partially-written row (or one written before a new field
        existed) never comes back missing a key."""
        stored = await self.get_raw(AI_CONFIG_KEY) or {}
        return {**DEFAULT_AI_CONFIG, **stored}

    async def set_ai_config(self, config: dict, updated_by: Optional[str] = None) -> dict:
        merged = {**DEFAULT_AI_CONFIG, **config}
        await self.set_raw(AI_CONFIG_KEY, merged, updated_by)
        # The LLM client is cached in-process (app/core/llm.py) - without
        # this, a saved change here wouldn't take effect until the next
        # process restart, defeating the entire point of this feature.
        from app.core.llm import invalidate_llm_cache

        invalidate_llm_cache()
        return merged

    async def get_feature_flags(self) -> dict:
        stored = await self.get_raw(FEATURE_FLAGS_KEY) or {}
        return {**DEFAULT_FEATURE_FLAGS, **stored}

    async def set_feature_flags(self, flags: dict, updated_by: Optional[str] = None) -> dict:
        merged = {**DEFAULT_FEATURE_FLAGS, **flags}
        await self.set_raw(FEATURE_FLAGS_KEY, merged, updated_by)
        return merged

    async def get_provider_keys(self) -> dict:
        """Raw {provider: api_key} - internal use only (app/core/llm.py).
        Never return this dict from an API response; see
        app/api/v1/endpoints/admin.py's masking for what the dashboard
        actually gets back."""
        return await self.get_raw(PROVIDER_KEYS_KEY) or {}

    async def set_provider_key(self, provider: str, api_key: str, updated_by: Optional[str] = None) -> None:
        """Set (or, with an empty string, clear) one provider's stored API
        key - a partial update, leaving every other provider's key
        untouched, unlike set_ai_config/set_feature_flags which replace
        the whole row."""
        current = await self.get_provider_keys()
        if api_key:
            current[provider] = api_key
        else:
            current.pop(provider, None)
        await self.set_raw(PROVIDER_KEYS_KEY, current, updated_by)
        # Same reasoning as set_ai_config - a key change must take effect
        # on the next chat turn, not after a restart.
        from app.core.llm import invalidate_llm_cache

        invalidate_llm_cache()
