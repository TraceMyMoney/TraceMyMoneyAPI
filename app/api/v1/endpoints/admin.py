from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AdminUser, DatabaseDep, UserServiceDep
from app.schemas.admin import (
    AdminSetChatbotAccess,
    AdminSetDisabled,
    AdminSetIsAdmin,
    AdminUserItem,
    AdminUserListResponse,
    AiConfig,
    FeatureFlags,
    LlmMetricsResponse,
    LlmStatusResponse,
    ProviderKeysStatusResponse,
    ProviderKeyStatus,
    SetProviderKey,
)
from app.services.app_settings_service import SUPPORTED_PROVIDERS, AppSettingsService

router = APIRouter()


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    admin_user: AdminUser,
    user_service: UserServiceDep,
    page_number: int = Query(1, ge=1),
    per_page: int = Query(5, ge=1, le=100),
    search: str | None = Query(None),
):
    """Admin-only: paginated user list for the admin dashboard."""
    page_users, total = await user_service.list_all_users(page_number=page_number, per_page=per_page, search=search)
    return AdminUserListResponse(
        users=[AdminUserItem(**u) for u in page_users],
        total=total,
        page_number=page_number,
        per_page=per_page,
    )


@router.patch("/users/{user_id}/chatbot", response_model=AdminUserItem)
async def set_user_chatbot_access(
    user_id: str,
    payload: AdminSetChatbotAccess,
    admin_user: AdminUser,
    user_service: UserServiceDep,
):
    """Admin-only: grant/revoke one user's access to the AI chatbot."""
    user = await user_service.set_chatbot_enabled(user_id, payload.chatbot_enabled)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserItem(**user)


@router.patch("/users/{user_id}/admin", response_model=AdminUserItem)
async def set_user_is_admin(
    user_id: str,
    payload: AdminSetIsAdmin,
    admin_user: AdminUser,
    user_service: UserServiceDep,
):
    """Admin-only: grant/revoke another user's admin access."""
    user = await user_service.set_is_admin(user_id, payload.is_admin)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserItem(**user)


@router.patch("/users/{user_id}/disabled", response_model=AdminUserItem)
async def set_user_disabled(
    user_id: str,
    payload: AdminSetDisabled,
    admin_user: AdminUser,
    user_service: UserServiceDep,
):
    """Admin-only: lock/unlock a user's account entirely (stronger than
    revoking chatbot access - blocks login outright)."""
    user = await user_service.set_is_disabled(user_id, payload.is_disabled)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserItem(**user)


@router.get("/ai-config", response_model=AiConfig)
async def get_ai_config(admin_user: AdminUser, db: DatabaseDep):
    """Admin-only: the currently active chat-LLM provider/model config."""
    config = await AppSettingsService(db).get_ai_config()
    return AiConfig(**config)


@router.put("/ai-config", response_model=AiConfig)
async def set_ai_config(payload: AiConfig, admin_user: AdminUser, db: DatabaseDep):
    """Admin-only: switch the chat-LLM provider/model. Takes effect on the
    very next chat turn - no redeploy or restart needed (see
    app/core/llm.py). The provider's API key must already be set in that
    environment's .env; this endpoint only picks which one is used."""
    config = await AppSettingsService(db).set_ai_config(payload.model_dump(), updated_by=admin_user.id)
    return AiConfig(**config)


@router.get("/feature-flags", response_model=FeatureFlags)
async def get_feature_flags(admin_user: AdminUser, db: DatabaseDep):
    """Admin-only: current runtime feature flags."""
    flags = await AppSettingsService(db).get_feature_flags()
    return FeatureFlags(**flags)


@router.put("/feature-flags", response_model=FeatureFlags)
async def set_feature_flags(payload: FeatureFlags, admin_user: AdminUser, db: DatabaseDep):
    """Admin-only: toggle runtime feature flags without a redeploy."""
    flags = await AppSettingsService(db).set_feature_flags(payload.model_dump(), updated_by=admin_user.id)
    return FeatureFlags(**flags)


def _mask(key: str) -> str:
    if len(key) <= 4:
        return "••••"
    return f"••••{key[-4:]}"


@router.get("/provider-keys", response_model=ProviderKeysStatusResponse)
async def get_provider_keys(admin_user: AdminUser, db: DatabaseDep):
    """Admin-only: per-provider API key *status* - never the real key (see
    ProviderKeyStatus). Shows whether each provider is usable right now
    and where that key came from (an admin-set DB value, or a .env
    fallback)."""
    from app.core.config import settings as env_settings

    stored = await AppSettingsService(db).get_provider_keys()
    env_fallback = {
        "groq": env_settings.GROQ_API_KEY,
        "openai": env_settings.OPENAI_API_KEY,
        "anthropic": env_settings.ANTHROPIC_API_KEY,
        "openrouter": env_settings.OPENROUTER_API_KEY,
    }
    statuses = {}
    for provider in SUPPORTED_PROVIDERS:
        db_key = stored.get(provider)
        if db_key:
            statuses[provider] = ProviderKeyStatus(configured=True, source="database", masked=_mask(db_key))
        elif env_fallback.get(provider):
            statuses[provider] = ProviderKeyStatus(configured=True, source="env", masked=_mask(env_fallback[provider]))
        else:
            statuses[provider] = ProviderKeyStatus(configured=False)
    return ProviderKeysStatusResponse(**statuses)


@router.put("/provider-keys", response_model=ProviderKeyStatus)
async def set_provider_key(payload: SetProviderKey, admin_user: AdminUser, db: DatabaseDep):
    """Admin-only: set (or, with an empty api_key, clear) one provider's
    API key. Takes effect on the next chat turn - see app/core/llm.py."""
    from app.core.config import settings as env_settings

    await AppSettingsService(db).set_provider_key(payload.provider, payload.api_key, updated_by=admin_user.id)
    if payload.api_key:
        return ProviderKeyStatus(configured=True, source="database", masked=_mask(payload.api_key))
    # Cleared the DB-stored key - report whether a .env fallback still
    # makes this provider usable, rather than always claiming "not set".
    env_fallback = {
        "groq": env_settings.GROQ_API_KEY,
        "openai": env_settings.OPENAI_API_KEY,
        "anthropic": env_settings.ANTHROPIC_API_KEY,
        "openrouter": env_settings.OPENROUTER_API_KEY,
    }.get(payload.provider)
    if env_fallback:
        return ProviderKeyStatus(configured=True, source="env", masked=_mask(env_fallback))
    return ProviderKeyStatus(configured=False)


@router.get("/llm-status", response_model=LlmStatusResponse)
async def get_llm_status(admin_user: AdminUser):
    """Admin-only: the most recent chat-LLM failure (e.g. a Groq rate
    limit, with the used/limit/retry numbers parsed out), if any - lets
    the dashboard show *why* chat is slow/erroring without reading server
    logs. None once a call has since succeeded."""
    from app.core.llm_status import get_last_llm_error

    return LlmStatusResponse(last_error=get_last_llm_error())


@router.get("/llm-metrics", response_model=LlmMetricsResponse)
async def get_llm_metrics(admin_user: AdminUser):
    """Admin-only: how many tokens chat requests are actually sending to
    the LLM - recent individual requests plus today/lifetime totals. See
    app/core/llm_metrics.py - process-local and reset on restart, an
    operational view, not a billing system of record."""
    from app.core.llm_metrics import get_metrics

    return LlmMetricsResponse(**get_metrics())
