from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator

from app.services.app_settings_service import SUPPORTED_PROVIDERS


class AdminUserItem(BaseModel):
    id: str
    username: str
    email: str
    is_admin: bool
    chatbot_enabled: bool
    is_disabled: bool
    created_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminUserItem]


class AdminSetChatbotAccess(BaseModel):
    chatbot_enabled: bool


class AdminSetIsAdmin(BaseModel):
    is_admin: bool


class AdminSetDisabled(BaseModel):
    is_disabled: bool


class AiConfig(BaseModel):
    """Which chat-LLM provider/model is active - see app/core/llm.py.
    `model=None` means "use that provider's configured default"."""

    provider: str = "groq"
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: int = 20
    max_retries: int = 1

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, v: str) -> str:
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unknown provider '{v}' - must be one of {SUPPORTED_PROVIDERS}")
        return v


class FeatureFlags(BaseModel):
    jev_fast_path_enabled: bool = True
    voice_input_enabled: bool = True


class ProviderKeyStatus(BaseModel):
    """Never carries the real key - just whether one is set (in the DB or
    via a .env fallback) and a masked hint, so the dashboard can show
    "configured" without the raw secret ever round-tripping back out over
    the network."""

    configured: bool
    source: Optional[str] = None  # "database" | "env" | None
    masked: Optional[str] = None  # e.g. "sk-...wxyz"


class ProviderKeysStatusResponse(BaseModel):
    groq: ProviderKeyStatus
    openai: ProviderKeyStatus
    anthropic: ProviderKeyStatus
    openrouter: ProviderKeyStatus


class SetProviderKey(BaseModel):
    provider: str
    api_key: str  # empty string clears the DB-stored key (falls back to .env, if any)

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, v: str) -> str:
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unknown provider '{v}' - must be one of {SUPPORTED_PROVIDERS}")
        return v


class LlmQuotaStatus(BaseModel):
    limit: int
    used: int
    requested: int
    retry_after_seconds: int


class LlmErrorStatus(BaseModel):
    provider: str
    message: str
    at: str
    quota: Optional[LlmQuotaStatus] = None


class LlmStatusResponse(BaseModel):
    last_error: Optional[LlmErrorStatus] = None
