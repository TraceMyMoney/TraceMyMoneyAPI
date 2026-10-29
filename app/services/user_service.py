import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import select, or_
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

    async def authenticate_user(self, username: str, password: str) -> Optional[UserModel]:
        """Authenticate user by username and password."""
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not verify_password(password, user.password):
            return None
        return user
