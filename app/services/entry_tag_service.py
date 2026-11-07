import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.tables import expense_entry_tags
from app.models.expense_entry_tag import ExpenseEntryTagModel
from app.schemas.entry_tag import EntryTagCreate, EntryTagUpdate
from app.services.user_service import is_valid_id


class EntryTagService:
    """Service for expense entry tag-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tag(self, user_id: str, tag_data: EntryTagCreate) -> ExpenseEntryTagModel:
        """Create a new entry tag."""
        existing = await self.db.execute(
            select(expense_entry_tags).where(
                expense_entry_tags.c.user_id == uuid.UUID(user_id), expense_entry_tags.c.name == tag_data.name
            )
        )
        if existing.first():
            raise ValueError(f"Tag with name '{tag_data.name}' already exists")

        new_id = uuid.uuid4()
        values = {
            "id": new_id,
            "user_id": uuid.UUID(user_id),
            "name": tag_data.name,
            "created_at": datetime.now(timezone.utc),
        }
        await self.db.execute(expense_entry_tags.insert().values(**values))
        await self.db.commit()

        return ExpenseEntryTagModel(**{**values, "_id": str(new_id)})

    async def get_tags(self, user_id: str) -> List[ExpenseEntryTagModel]:
        """Get all tags for a user."""
        result = await self.db.execute(
            select(expense_entry_tags).where(expense_entry_tags.c.user_id == uuid.UUID(user_id))
        )
        rows = result.mappings().all()
        return [ExpenseEntryTagModel(**{**row, "_id": str(row["id"])}) for row in rows]

    async def get_tag_by_id(self, user_id: str, tag_id: str) -> Optional[ExpenseEntryTagModel]:
        """Get a specific tag."""
        if not is_valid_id(tag_id):
            return None

        result = await self.db.execute(
            select(expense_entry_tags).where(
                expense_entry_tags.c.id == uuid.UUID(tag_id), expense_entry_tags.c.user_id == uuid.UUID(user_id)
            )
        )
        row = result.mappings().first()
        if row:
            return ExpenseEntryTagModel(**{**row, "_id": str(row["id"])})
        return None

    async def update_tag(
        self, user_id: str, tag_id: str, tag_data: EntryTagUpdate
    ) -> Optional[ExpenseEntryTagModel]:
        """Update a tag."""
        if not is_valid_id(tag_id):
            return None

        update_data = tag_data.model_dump(exclude_unset=True)
        if not update_data:
            return None

        result = await self.db.execute(
            expense_entry_tags.update()
            .where(expense_entry_tags.c.id == uuid.UUID(tag_id), expense_entry_tags.c.user_id == uuid.UUID(user_id))
            .values(**update_data)
            .returning(*expense_entry_tags.c)
        )
        row = result.mappings().first()
        await self.db.commit()

        if row:
            return ExpenseEntryTagModel(**{**row, "_id": str(row["id"])})
        return None

    async def delete_tag(self, user_id: str, tag_id: str) -> bool:
        """Delete a tag."""
        if not is_valid_id(tag_id):
            return False

        result = await self.db.execute(
            expense_entry_tags.delete().where(
                expense_entry_tags.c.id == uuid.UUID(tag_id), expense_entry_tags.c.user_id == uuid.UUID(user_id)
            )
        )
        await self.db.commit()
        return result.rowcount > 0
