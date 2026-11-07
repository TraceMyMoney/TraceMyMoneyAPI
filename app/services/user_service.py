import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.tables import users
from app.models.user import UserModel
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password


def is_valid_id(v: str) -> bool:
    """Validate a UUID-formatted ID string."""
    try:
        uuid.UUID(str(v))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class UserService:
    """Service for user-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, user_data: UserCreate) -> UserModel:
        """Create a new user."""
        existing = await self.db.execute(
            select(users).where(or_(users.c.email == user_data.email, users.c.username == user_data.username))
        )
        if existing.first():
            raise ValueError("User already exists either with given username or email")

        now = datetime.now(timezone.utc)
        new_id = uuid.uuid4()
        values = {
            "id": new_id,
            "username": user_data.username,
            "email": user_data.email,
            "password": get_password_hash(user_data.password),
            "is_subscribed_to_emails": user_data.is_subscribed_to_emails,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.execute(users.insert().values(**values))
        await self.db.commit()

        return UserModel(**{**values, "_id": str(new_id)})

    async def get_user_by_id(self, user_id: str) -> Optional[UserModel]:
        """Get user by ID."""
        if not is_valid_id(user_id):
            return None

        result = await self.db.execute(select(users).where(users.c.id == uuid.UUID(user_id)))
        row = result.mappings().first()
        if row:
            return UserModel(**{**row, "_id": str(row["id"])})
        return None

    async def get_user_by_email(self, email: str) -> Optional[UserModel]:
        """Get user by email."""
        result = await self.db.execute(select(users).where(users.c.email == email))
        row = result.mappings().first()
        if row:
            return UserModel(**{**row, "_id": str(row["id"])})
        return None

    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        """Get user by username."""
        result = await self.db.execute(select(users).where(users.c.username == username))
        row = result.mappings().first()
        if row:
            return UserModel(**{**row, "_id": str(row["id"])})
        return None

    async def update_user(self, user_id: str, user_data: UserUpdate) -> Optional[UserModel]:
        """Update user."""
        if not is_valid_id(user_id):
            return None

        update_data = user_data.model_dump(exclude_unset=True)

        if "password" in update_data:
            update_data["password"] = get_password_hash(update_data.pop("password"))

        update_data["updated_at"] = datetime.now(timezone.utc)

        result = await self.db.execute(
            users.update().where(users.c.id == uuid.UUID(user_id)).values(**update_data).returning(*users.c)
        )
        row = result.mappings().first()
        await self.db.commit()

        if row:
            return UserModel(**{**row, "_id": str(row["id"])})
        return None

    async def list_all_users(
        self, page_number: int = 1, per_page: int = 5, search: Optional[str] = None
    ) -> tuple[List[dict], int]:
        """Paginated user list - admin dashboard only (see
        app/api/v1/endpoints/admin.py). Returns raw rows, not UserModel -
        some legacy/migrated accounts (e.g. a 3-char username) don't meet
        UserModel's current validators, which would otherwise make the
        whole listing 500 just because one old row fails validation on
        construction; the admin schema (AdminUserItem) has no such
        constraint. Returns (rows, total_count) - total reflects the
        search filter, not the whole table, so the UI can page through
        just the matching set."""
        stmt = select(users)
        count_stmt = select(func.count()).select_from(users)

        if search and search.strip():
            like = f"%{search.strip()}%"
            cond = or_(users.c.username.ilike(like), users.c.email.ilike(like))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await self.db.execute(count_stmt)).scalar_one()

        skip = max(0, (page_number - 1) * per_page)
        stmt = stmt.order_by(users.c.created_at.desc()).limit(per_page).offset(skip)

        result = await self.db.execute(stmt)
        rows = result.mappings().all()
        return [{**row, "id": str(row["id"])} for row in rows], total

    async def set_chatbot_enabled(self, user_id: str, enabled: bool) -> Optional[dict]:
        """Grant/revoke one user's access to the AI chatbot - admin-only.
        Returns a raw row for the same reason as list_all_users above."""
        return await self._update_flag(user_id, chatbot_enabled=enabled)

    async def set_is_admin(self, user_id: str, is_admin: bool) -> Optional[dict]:
        """Grant/revoke admin access - admin-only. Deliberately doesn't stop
        an admin from revoking their own access (no extra special-casing);
        if that locks everyone out, it's recoverable directly in the DB,
        same as any other misconfiguration."""
        return await self._update_flag(user_id, is_admin=is_admin)

    async def set_is_disabled(self, user_id: str, is_disabled: bool) -> Optional[dict]:
        """Lock/unlock a user's account entirely - admin-only. Enforced on
        every authenticated request (app/api/deps.get_current_user), not
        just login, so disabling takes effect immediately even for an
        already-logged-in session."""
        return await self._update_flag(user_id, is_disabled=is_disabled)

    async def _update_flag(self, user_id: str, **values) -> Optional[dict]:
        if not is_valid_id(user_id):
            return None
        result = await self.db.execute(
            users.update()
            .where(users.c.id == uuid.UUID(user_id))
            .values(**values, updated_at=datetime.now(timezone.utc))
            .returning(*users.c)
        )
        row = result.mappings().first()
        await self.db.commit()
        if row:
            return {**row, "id": str(row["id"])}
        return None

    async def authenticate_user(self, username: str, password: str) -> Optional[UserModel]:
        """Authenticate user by username and password."""
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not verify_password(password, user.password):
            return None
        return user
