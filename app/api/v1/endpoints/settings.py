"""Read-only, any-authenticated-user access to a subset of app_settings -
specifically feature flags the frontend needs to know about for every
user (e.g. whether to show the chat voice-input button), as opposed to
app/api/v1/endpoints/admin.py's admin-only read/write access to the full
settings surface (AI provider config, user management, etc.)."""

from fastapi import APIRouter
from app.api.deps import CurrentUser, DatabaseDep
from app.schemas.admin import FeatureFlags
from app.services.app_settings_service import AppSettingsService

router = APIRouter()


@router.get("/feature-flags", response_model=FeatureFlags)
async def get_feature_flags(current_user: CurrentUser, db: DatabaseDep):
    flags = await AppSettingsService(db).get_feature_flags()
    return FeatureFlags(**flags)
