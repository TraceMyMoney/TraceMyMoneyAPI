from typing import List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.models.expense_entry_tag import ExpenseEntryTagModel
from app.schemas.entry_tag import EntryTagCreate, EntryTagUpdate


class EntryTagService:
    """Service for expense entry tag-related business logic."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.expense_entry_tags

    async def create_tag(self, user_id: str, tag_data: EntryTagCreate) -> ExpenseEntryTagModel:
        """Create a new entry tag."""
        # Check if tag with same name already exists for user
        existing = await self.collection.find_one({"user_id": user_id, "name": tag_data.name})
        if existing:
            raise ValueError(f"Tag with name '{tag_data.name}' already exists")

        tag_dict = tag_data.model_dump()
        tag_dict["user_id"] = user_id
        tag_dict["created_at"] = datetime.utcnow()

        result = await self.collection.insert_one(tag_dict)
        tag_dict["_id"] = str(result.inserted_id)

        return ExpenseEntryTagModel(**tag_dict)

    async def get_tags(self, user_id: str) -> List[ExpenseEntryTagModel]:
        """Get all tags for a user."""
        cursor = self.collection.find({"user_id": user_id})
        tags = await cursor.to_list(length=None)

        for tag in tags:
            tag["_id"] = str(tag["_id"])

        return [ExpenseEntryTagModel(**tag) for tag in tags]

    async def get_tag_by_id(self, user_id: str, tag_id: str) -> Optional[ExpenseEntryTagModel]:
        """Get a specific tag."""
        if not ObjectId.is_valid(tag_id):
            return None

        tag = await self.collection.find_one({"_id": ObjectId(tag_id), "user_id": user_id})
        if tag:
            tag["_id"] = str(tag["_id"])
            return ExpenseEntryTagModel(**tag)
        return None

    async def update_tag(
        self, user_id: str, tag_id: str, tag_data: EntryTagUpdate
    ) -> Optional[ExpenseEntryTagModel]:
        """Update a tag."""
        if not ObjectId.is_valid(tag_id):
            return None

        update_data = tag_data.model_dump(exclude_unset=True)

        if not update_data:
            return None

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(tag_id), "user_id": user_id}, {"$set": update_data}, return_document=True
        )

        if result:
            result["_id"] = str(result["_id"])
            return ExpenseEntryTagModel(**result)
        return None

    async def delete_tag(self, user_id: str, tag_id: str) -> bool:
        """Delete a tag."""
        if not ObjectId.is_valid(tag_id):
            return False

        result = await self.collection.delete_one({"_id": ObjectId(tag_id), "user_id": user_id})
        return result.deleted_count > 0
