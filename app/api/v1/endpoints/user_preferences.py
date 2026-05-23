from fastapi import APIRouter
from app.api.deps import CurrentUser, UserPreferenceServiceDep
from app.schemas.user_preference import UserPreferenceUpdate, UserPreferenceResponse, UserPreferenceNoContentResponse

router = APIRouter()


@router.get("/")
async def get_user_preferences(current_user: CurrentUser, pref_service: UserPreferenceServiceDep) -> UserPreferenceResponse:
    prefs = await pref_service.get_or_create_preferences(current_user.id)

    return {
        "page_size": prefs.page_size,
        "is_dark_mode": prefs.is_dark_mode,
        "privacy_mode_enabled": prefs.privacy_mode_enabled,
        "banks_display_order": prefs.banks_display_order
    }


@router.patch("/update", status_code=200)
async def update_user_preferences(
    pref_data: UserPreferenceUpdate, current_user: CurrentUser, pref_service: UserPreferenceServiceDep
) -> UserPreferenceNoContentResponse :
    """Update user preferences."""
    prefs = await pref_service.update_preferences(current_user.id, pref_data)
    return {"message": "SUCCESS"}
