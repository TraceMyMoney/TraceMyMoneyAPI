from datetime import timedelta
from fastapi import APIRouter, HTTPException, status
from app.api.deps import UserServiceDep
from app.schemas.token import Token, LoginRequest, RefreshRequest
from app.schemas.user import UserCreate
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.core.config import settings

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest, user_service: UserServiceDep):
    """
    Login with username and password to get a JWT access token.
    Matches Flask response format: {"token": "...", "status_code": 200}
    """
    user = await user_service.authenticate_user(
        credentials.username, credentials.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid username or password",
        )

    payload = {"user_id": user.id, "user_name": user.username}
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data=payload,
        expires_delta=access_token_expires,
    )

    refresh_token = create_refresh_token(
        data=payload,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )

    return {"token": access_token, "refresh_token": refresh_token, "status_code": 200}


@router.post("/register", status_code=200)
async def register(user_data: UserCreate, user_service: UserServiceDep):
    """
    Register a new user.
    Returns success message matching Flask format.
    """
    try:
        created_user = await user_service.create_user(user_data)
        return {"success": "User created successfully", "user_id": created_user.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/refresh", response_model=Token)
async def refresh_access_token(body: RefreshRequest):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    refresh_token_value = body.refresh_token.replace("Bearer ", "").replace("bearer ", "").strip()
    payload = decode_refresh_token(refresh_token_value)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("user_id")
    user_name = payload.get("user_name")
    if user_id is None:
        raise credentials_exception

    new_payload = {"user_id": user_id, "user_name": user_name}

    new_access_token = create_access_token(
        data=new_payload,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    new_refresh_token = create_refresh_token(
        data=new_payload,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )

    return {
        "token": new_access_token,
        "refresh_token": new_refresh_token,
        "status_code": 200,
    }
