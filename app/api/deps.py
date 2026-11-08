from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.postgres import get_postgres_session
from app.models.user import UserModel
from app.services.bank_service import BankService
from app.services.entry_tag_service import EntryTagService
from app.services.expense_service import ExpenseService
from app.services.ingest_service import IngestService
from app.services.user_preference_service import UserPreferenceService
from app.services.user_service import UserService


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


async def get_ingest_service(db: AsyncSession = Depends(get_db)) -> IngestService:
    """Dependency to get ingest (SMS webhook + inbox) service instance."""
    return IngestService(db)


async def get_ingest_user_id(
    ingest: IngestService = Depends(get_ingest_service),
    x_ingest_token: str | None = Header(None),
    authorization: str | None = Header(None),
    user_service: UserService = Depends(get_user_service),
) -> str:
    """Authenticate the SMS webhook by its personal token (X-Ingest-Token, or
    `Authorization: Bearer smm_...`). Returns the owning user's id."""
    token = x_ingest_token
    if not token and authorization:
        token = authorization.replace("Bearer ", "").replace("bearer ", "")
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ingest token")
    if not token or not token.startswith("smm_"):
        raise unauthorized
    user_id = await ingest.user_id_for_token(token)
    if user_id is None:
        raise unauthorized
    user = await user_service.get_user_by_id(user_id)
    if user is None or user.is_disabled:
        raise unauthorized
    return user_id


async def get_current_user(
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None),
) -> UserModel:
    """Get current authenticated user from the Authorization header.

    Accepts the app's own JWT, or a Claude connector OAuth access token (what
    the MCP server forwards) - looked up in oauth_tokens when it isn't a JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
    )

    if not authorization:
        raise credentials_exception

    # Extract token - handle both "Bearer token" and just "token"
    token = authorization.replace("Bearer ", "").replace("bearer ", "")

    payload = decode_access_token(token)
    if payload is None:
        # Not a JWT: maybe an OAuth connector token (opaque, no dots).
        from app.services.oauth_service import OAuthService

        oauth_user = await OAuthService(db).user_for_token(token)
        if oauth_user is None:
            raise credentials_exception
        payload = {"user_id": oauth_user["id"]}

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
IngestServiceDep = Annotated[IngestService, Depends(get_ingest_service)]
IngestUser = Annotated[str, Depends(get_ingest_user_id)]
