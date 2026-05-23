from datetime import timedelta
from fastapi import APIRouter, HTTPException, status
from app.api.deps import UserServiceDep
from app.schemas.token import Token, LoginRequest
from app.schemas.user import UserCreate
from app.core.security import create_access_token
from app.core.config import settings

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

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"user_id": user.id, "user_name": user.username}, expires_delta=access_token_expires
    )

    return {"token": access_token, "status_code": 200}


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
