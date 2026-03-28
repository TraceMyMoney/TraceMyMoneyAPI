from typing import Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.models.user import UserModel
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password


class UserService:
    """Service for user-related business logic."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.user

    async def create_user(self, user_data: UserCreate) -> UserModel:
        """Create a new user."""
        # Check if user already exists
        existing_user = await self.collection.find_one(
            {"$or": [{"email": user_data.email}, {"username": user_data.username}]}
        )

        if existing_user:
            raise ValueError("User already exists either with given username or email")

        # Create user document
        user_dict = user_data.model_dump(exclude={"password"})
        user_dict["password"] = get_password_hash(user_data.password)
        user_dict["created_at"] = datetime.utcnow()
        user_dict["updated_at"] = datetime.utcnow()

        result = await self.collection.insert_one(user_dict)
        user_dict["_id"] = str(result.inserted_id)

        return UserModel(**user_dict)

    async def get_user_by_id(self, user_id: str) -> Optional[UserModel]:
        """Get user by ID."""
        if not ObjectId.is_valid(user_id):
            return None

        user = await self.collection.find_one({"_id": ObjectId(user_id)})
        if user:
            user["_id"] = str(user["_id"])
            return UserModel(**user)
        return None

    async def get_user_by_email(self, email: str) -> Optional[UserModel]:
        """Get user by email."""
        user = await self.collection.find_one({"email": email})
        if user:
            user["_id"] = str(user["_id"])
            return UserModel(**user)
        return None

    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        """Get user by username."""
        user = await self.collection.find_one({"username": username})
        if user:
            user["_id"] = str(user["_id"])
            return UserModel(**user)
        return None

    async def update_user(self, user_id: str, user_data: UserUpdate) -> Optional[UserModel]:
        """Update user."""
        if not ObjectId.is_valid(user_id):
            return None

        update_data = user_data.model_dump(exclude_unset=True)

        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

        update_data["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(user_id)}, {"$set": update_data}, return_document=True
        )

        if result:
            result["_id"] = str(result["_id"])
            return UserModel(**result)
        return None

    async def authenticate_user(self, username: str, password: str) -> Optional[UserModel]:
        """Authenticate user by username and password."""
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not verify_password(password, user.password):
            return None
        return user
