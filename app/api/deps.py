from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import get_postgres_session
from app.core.security import decode_access_token
from app.services.user_service import UserService
from app.services.bank_service import BankService
from app.services.expense_service import ExpenseService
from app.services.entry_tag_service import EntryTagService
from app.services.user_preference_service import UserPreferenceService
from app.models.user import UserModel


async def get_db(session: AsyncSession = Depends(get_postgres_session)) -> AsyncSession:
    """Dependency to get database session instance."""
    return session


async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    """Dependency to get user service instance."""
    return UserService(db)


async def get_bank_service(db: AsyncSession = Depends(get_db)) -> BankService:
    """Dependency to get bank service instance."""
    return BankService(db)


async def get_expense_service(db: AsyncSession = Depends(get_db)) -> ExpenseService:
    """Dependency to get expense service instance."""
    return ExpenseService(db)


async def get_entry_tag_service(db: AsyncSession = Depends(get_db)) -> EntryTagService:
    """Dependency to get entry tag service instance."""
    return EntryTagService(db)


async def get_user_preference_service(db: AsyncSession = Depends(get_db)) -> UserPreferenceService:
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
    if user.is_disabled:
        # Checked on every request (not just login) so an admin disabling a
        # user mid-session revokes access immediately, not just on their
        # next login - an already-issued JWT would otherwise keep working
        # until it expires.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled")

    return user


async def get_current_admin_user(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    """Same as get_current_user, but 403s anyone who isn't an admin - for
    admin-only endpoints like the user-management dashboard."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


# Type aliases for cleaner endpoint signatures
CurrentUser = Annotated[UserModel, Depends(get_current_user)]
AdminUser = Annotated[UserModel, Depends(get_current_admin_user)]
DatabaseDep = Annotated[AsyncSession, Depends(get_db)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
BankServiceDep = Annotated[BankService, Depends(get_bank_service)]
ExpenseServiceDep = Annotated[ExpenseService, Depends(get_expense_service)]
EntryTagServiceDep = Annotated[EntryTagService, Depends(get_entry_tag_service)]
UserPreferenceServiceDep = Annotated[UserPreferenceService, Depends(get_user_preference_service)]
