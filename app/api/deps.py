from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status, Header
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.session import get_database
from app.core.security import decode_access_token
from app.services.user_service import UserService
from app.services.bank_service import BankService
from app.services.expense_service import ExpenseService
from app.services.entry_tag_service import EntryTagService
from app.services.user_preference_service import UserPreferenceService
from app.models.user import UserModel


async def get_db() -> AsyncIOMotorDatabase:
    """Dependency to get database instance."""
    return get_database()


async def get_user_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> UserService:
    """Dependency to get user service instance."""
    return UserService(db)


async def get_bank_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> BankService:
    """Dependency to get bank service instance."""
    return BankService(db)


async def get_expense_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> ExpenseService:
    """Dependency to get expense service instance."""
    return ExpenseService(db)


async def get_entry_tag_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> EntryTagService:
    """Dependency to get entry tag service instance."""
    return EntryTagService(db)


async def get_user_preference_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> UserPreferenceService:
    """Dependency to get user preference service instance."""
    return UserPreferenceService(db)


async def get_current_user(
    user_service: UserService = Depends(get_user_service), authorization: Optional[str] = Header(None)
) -> UserModel:
    """Get current authenticated user from JWT token in Authorization header."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
    )

    if not authorization:
        raise credentials_exception

    # Extract token - handle both "Bearer token" and just "token"
    token = authorization.replace("Bearer ", "").replace("bearer ", "")

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("user_id")
    if user_id is None:
        raise credentials_exception

    user = await user_service.get_user_by_id(user_id)
    if user is None:
        raise credentials_exception

    return user


# Type aliases for cleaner endpoint signatures
CurrentUser = Annotated[UserModel, Depends(get_current_user)]
DatabaseDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
BankServiceDep = Annotated[BankService, Depends(get_bank_service)]
ExpenseServiceDep = Annotated[ExpenseService, Depends(get_expense_service)]
EntryTagServiceDep = Annotated[EntryTagService, Depends(get_entry_tag_service)]
UserPreferenceServiceDep = Annotated[UserPreferenceService, Depends(get_user_preference_service)]
