"""
The chat-LLM client used by the agent (app/services/agent/agent_service.py).

Admin-configurable, without a redeploy: `get_llm(db)` reads the active
provider/model from the app_settings DB row (app/services/
app_settings_service.py - edited via the admin dashboard's AI config
panel) and lazily builds/caches a client for it. The cache is a single
process-wide slot, invalidated by AppSettingsService.set_ai_config/
set_provider_key whenever an admin saves a change, so a save takes effect
on the very next chat turn with no restart.

Each provider's API key can be set from the admin dashboard (stored in
app_settings, see AppSettingsService.get_provider_keys) - this is the
*intended* way to configure a new provider. A .env value
(GROQ_API_KEY/OPENAI_API_KEY/ANTHROPIC_API_KEY/OPENROUTER_API_KEY) is only
a fallback for whichever provider has no DB-stored key, mainly so Groq
keeps working out of the box via the original env var. If the configured
provider ends up with no key anywhere, or the provider/model is otherwise
unusable, get_llm() logs and silently falls back to the original
GROQ_MODEL_NAME/GROQ_API_KEY env-based ChatGroq client - a bad admin
config must never take the chatbot down entirely.
"""

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_cached_llm = None
_cached_key: Optional[tuple] = None
_last_provider = "groq"

SUPPORTED_PROVIDERS = ("groq", "openai", "anthropic", "openrouter")

# Each entry: provider name -> () -> env-var fallback api key (possibly
# empty) - only consulted when no DB-stored key exists for that provider.
_ENV_FALLBACK_KEYS = {
    "groq": lambda: settings.GROQ_API_KEY,
    "openai": lambda: settings.OPENAI_API_KEY,
    "anthropic": lambda: settings.ANTHROPIC_API_KEY,
    "openrouter": lambda: settings.OPENROUTER_API_KEY,
}

DEFAULT_AI_CONFIG = {
    "provider": "groq",
    "model": settings.GROQ_MODEL_NAME,
    "temperature": None,
    "max_tokens": None,
    "timeout": 20,
    "max_retries": 1,
}


def invalidate_llm_cache() -> None:
    """Drop the cached client so the next get_llm() rebuilds from
    scratch - called whenever an admin saves a new ai_config or API key."""
    global _cached_llm, _cached_key
    _cached_llm = None
    _cached_key = None


def current_provider() -> str:
    """The provider the most recently built/cached client belongs to -
    used only to label app/core/llm_status.py's error record; never part
    of request handling."""
    return _last_provider


def build_llm(config: dict, api_key: str):
    """Construct a chat-model client for the given ai_config dict and an
    already-resolved API key (caller decides DB-vs-env precedence - see
    get_llm). Raises ValueError for a bad/unknown provider or missing key;
    whatever the underlying langchain client raises for anything else -
    callers decide how to handle failure."""
    provider = config.get("provider") or "groq"
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown LLM provider '{provider}'")
    if not api_key:
        raise ValueError(f"No API key configured for provider '{provider}'")

    model = config.get("model") or DEFAULT_AI_CONFIG["model"]
    kwargs = {}
    if config.get("temperature") is not None:
        kwargs["temperature"] = config["temperature"]
    if config.get("max_tokens") is not None:
        kwargs["max_tokens"] = config["max_tokens"]
    timeout = config.get("timeout", DEFAULT_AI_CONFIG["timeout"])
    max_retries = config.get("max_retries", DEFAULT_AI_CONFIG["max_retries"])

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, api_key=api_key, timeout=timeout, max_retries=max_retries, **kwargs)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=api_key, timeout=timeout, max_retries=max_retries, **kwargs)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, api_key=api_key, timeout=timeout, max_retries=max_retries, **kwargs)
    if provider == "openrouter":
        # OpenRouter is OpenAI-API-compatible - same client, pointed at a
        # different base_url, same as every other OpenAI-compatible proxy.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout,
            max_retries=max_retries,
            **kwargs,
        )
    raise ValueError(f"Unknown LLM provider '{provider}'")  # pragma: no cover - guarded above


def _resolve_api_key(provider: str, stored_keys: dict) -> str:
    """DB-stored key wins when set; otherwise fall back to that provider's
    .env value (mainly keeps Groq working out of the box via the original
    GROQ_API_KEY, without requiring a trip through the admin UI)."""
    stored = (stored_keys or {}).get(provider)
    if stored:
        return stored
    return _ENV_FALLBACK_KEYS.get(provider, lambda: "")()


async def get_llm(db):
    """The currently active chat-LLM client. `db` is an AsyncSession, used
    only to read the admin-configured ai_config/provider keys - never
    raises, always returns a usable client (falling back to the env-based
    Groq default on any failure)."""
    global _cached_llm, _cached_key, _last_provider

    from app.services.app_settings_service import AppSettingsService

    try:
        settings_service = AppSettingsService(db)
        config = await settings_service.get_ai_config()
        stored_keys = await settings_service.get_provider_keys()
    except Exception:
        logger.exception("Failed to read ai_config/provider keys from app_settings - using default Groq client")
        config = DEFAULT_AI_CONFIG
        stored_keys = {}

    api_key = _resolve_api_key(config.get("provider") or "groq", stored_keys)
    key = (tuple(sorted(config.items())), api_key)
    if _cached_llm is not None and _cached_key == key:
        return _cached_llm

    try:
        llm = build_llm(config, api_key)
        _last_provider = config.get("provider") or "groq"
    except Exception:
        logger.exception(
            "Failed to build configured LLM (provider=%s) - falling back to default Groq client",
            config.get("provider"),
        )
        default_key = _resolve_api_key("groq", stored_keys)
        llm = build_llm(DEFAULT_AI_CONFIG, default_key)
        key = (tuple(sorted(DEFAULT_AI_CONFIG.items())), default_key)
        _last_provider = "groq"

    _cached_llm = llm
    _cached_key = key
    return llm
