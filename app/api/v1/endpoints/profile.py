from datetime import timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, UserServiceDep
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.schemas.profile import PasswordChange, ProfileUpdate

router = APIRouter()


def _profile(user) -> dict:
    return {"username": user.username, "email": user.email, "created_at": user.created_at.isoformat()}


@router.get("/")
async def get_profile(current_user: CurrentUser):
    return _profile(current_user)


@router.patch("/")
async def update_profile(payload: ProfileUpdate, current_user: CurrentUser, user_service: UserServiceDep):
    """Change username and/or email. Returns fresh tokens too, because the
    username is carried inside the login token."""
    try:
        user = await user_service.update_profile(current_user.id, payload.username, payload.email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    access = create_access_token(
        data={
            "user_id": user.id,
            "user_name": user.username,
            "is_admin": user.is_admin,
            "chatbot_enabled": user.chatbot_enabled,
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh = create_refresh_token(data={"user_id": user.id, "user_name": user.username})
    return {**_profile(user), "token": access, "refresh_token": refresh}


@router.post("/password")
async def change_password(payload: PasswordChange, current_user: CurrentUser, user_service: UserServiceDep):
    try:
        await user_service.change_password(current_user.id, payload.current_password, payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"message": "SUCCESS"}
