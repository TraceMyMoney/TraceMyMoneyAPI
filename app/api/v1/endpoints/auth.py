from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AccountEmailServiceDep, UserServiceDep
from app.core.rate_limit import rate_limited
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token
from app.schemas.token import EmailRequest, LoginRequest, RefreshRequest, ResetPasswordRequest, Token, TokenRequest
from app.schemas.user import UserCreate

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest, user_service: UserServiceDep):
    """
    Login with username and password to get a JWT access token.
    Matches Flask response format: {"token": "...", "status_code": 200}
    """
    user = await user_service.authenticate_user(credentials.username, credentials.password)

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid username or password")
    if user.is_disabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled")
    if user.email_verified_at is None:
        # The UI matches on this prefix to offer "resend confirmation email".
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please confirm your email - check your inbox for the link.",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "user_id": user.id,
            "user_name": user.username,
            "is_admin": user.is_admin,
            "chatbot_enabled": user.chatbot_enabled,
        },
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(data={"user_id": user.id, "user_name": user.username})

    return {"token": access_token, "refresh_token": refresh_token, "status_code": 200}


@router.post("/refresh", response_model=Token)
async def refresh(request: RefreshRequest, user_service: UserServiceDep):
    """
    Exchange a refresh token for a new access token (and a rotated refresh token).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate refresh token"
    )

    payload = decode_refresh_token(request.refresh_token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("user_id")
    if user_id is None:
        raise credentials_exception

    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise credentials_exception
    if user.is_disabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "user_id": user.id,
            "user_name": user.username,
            "is_admin": user.is_admin,
            "chatbot_enabled": user.chatbot_enabled,
        },
        expires_delta=access_token_expires,
    )
    new_refresh_token = create_refresh_token(data={"user_id": user.id, "user_name": user.username})

    return {"token": access_token, "refresh_token": new_refresh_token, "status_code": 200}


@router.post("/register", status_code=200)
async def register(user_data: UserCreate, user_service: UserServiceDep, account_email: AccountEmailServiceDep):
    """
    Register a new user and queue the "confirm your email" message.
    The email is only queued here (a few ms); the background worker sends it,
    so signup never waits on the mail server.
    """
    try:
        created_user = await user_service.create_user(user_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await account_email.start_verification(created_user.id)
    return {
        "success": "User created successfully",
        "user_id": created_user.id,
        "message": "Check your email to confirm your account.",
    }


_GENERIC_SENT = {"message": "If that email is registered, we've sent a message to it."}


@router.post("/verify-email", dependencies=[Depends(rate_limited("verify-email", 20, 3600))])
async def verify_email(body: TokenRequest, account_email: AccountEmailServiceDep):
    """Confirm an account from the emailed link."""
    if not await account_email.verify(body.token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This link is invalid or has expired.")
    return {"message": "Email confirmed. You can log in now."}


@router.post("/resend-verification", dependencies=[Depends(rate_limited("resend-verification", 5, 3600))])
async def resend_verification(body: EmailRequest, account_email: AccountEmailServiceDep):
    """Always answers the same, whether or not the email is registered."""
    await account_email.resend_verification(body.email)
    return _GENERIC_SENT


@router.post("/forgot-password", dependencies=[Depends(rate_limited("forgot-password", 5, 3600))])
async def forgot_password(body: EmailRequest, account_email: AccountEmailServiceDep):
    """Always answers the same, whether or not the email is registered."""
    await account_email.request_password_reset(body.email)
    return _GENERIC_SENT


@router.post("/reset-password", dependencies=[Depends(rate_limited("reset-password", 10, 3600))])
async def reset_password(body: ResetPasswordRequest, account_email: AccountEmailServiceDep):
    """Set a new password using the emailed link."""
    if len(body.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters long.")
    if not await account_email.reset_password(body.token, body.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This link is invalid or has expired.")
    return {"message": "Password updated. You can log in now."}
