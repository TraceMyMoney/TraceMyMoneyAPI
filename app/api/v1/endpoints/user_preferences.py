from fastapi import APIRouter, HTTPException, status
from app.api.deps import CurrentUser, UserPreferenceServiceDep
from app.schemas.user_preference import UserPreferenceUpdate, UserPreferenceResponse

router = APIRouter()


@router.get("/")
async def get_user_preferences(current_user: CurrentUser, pref_service: UserPreferenceServiceDep):
    """Get user preferences."""
    prefs = await pref_service.get_or_create_preferences(current_user.id)

    return {
        "user_preferences": {
            "page_size": prefs.page_size,
            "is_dark_mode": prefs.is_dark_mode,
            "privacy_mode_enabled": prefs.privacy_mode_enabled,
        }
    }


@router.patch("/update", status_code=200)
async def update_user_preferences(
    pref_data: UserPreferenceUpdate, current_user: CurrentUser, pref_service: UserPreferenceServiceDep
):
    """Update user preferences."""
    prefs = await pref_service.update_preferences(current_user.id, pref_data)

    return {
        "success": "Preferences updated successfully",
        "user_preferences": {
            "page_size": prefs.page_size,
            "is_dark_mode": prefs.is_dark_mode,
            "privacy_mode_enabled": prefs.privacy_mode_enabled,
        },
    }
