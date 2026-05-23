from typing import Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.models.user_preference import UserPreferenceModel
from app.schemas.user_preference import UserPreferenceCreate, UserPreferenceUpdate


class UserPreferenceService:
    """Service for user preference-related business logic."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.user_preference

    async def get_or_create_preferences(self, user_id: str) -> UserPreferenceModel:
        """Get user preferences or create default if doesn't exist."""
        prefs = await self.collection.find_one({"user_id": user_id})

        if not prefs:
            # Create default preferences
            prefs = {
                "user_id": user_id,
                "page_size": 5,
                "is_dark_mode": False,
                "privacy_mode_enabled": False,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            result = await self.collection.insert_one(prefs)
            prefs["_id"] = str(result.inserted_id)
        else:
            prefs["_id"] = str(prefs["_id"])

        return UserPreferenceModel(**prefs)

    async def update_preferences(
        self, user_id: str, pref_data: UserPreferenceUpdate
    ) -> UserPreferenceModel:
        """Update user preferences."""
        update_data = pref_data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.utcnow()

        # Upsert (update or insert if doesn't exist)
        result = await self.collection.find_one_and_update(
            {"user_id": user_id}, {"$set": update_data}, upsert=True, return_document=True
        )

        if result:
            result["_id"] = str(result["_id"])
            return UserPreferenceModel(**result)

        # If still None, create new
        return await self.get_or_create_preferences(user_id)
