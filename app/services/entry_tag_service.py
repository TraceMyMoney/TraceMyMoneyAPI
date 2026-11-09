import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import expense_entry_tag_links, expense_entry_tags, user_preferences
from app.models.expense_entry_tag import ExpenseEntryTagModel
from app.schemas.entry_tag import EntryTagCreate, EntryTagUpdate, normalize_tag_name
from app.services.user_service import is_valid_id


class EntryTagService:
    """Service for expense entry tag-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _to_model(row, entry_count: int = 0) -> ExpenseEntryTagModel:
        data = {k: v for k, v in dict(row).items() if k != "entry_count"}
        return ExpenseEntryTagModel(**{**data, "_id": str(row["id"]), "entry_count": entry_count})

    async def _name_taken(self, user_id: str, name: str, exclude_tag_id: str | None = None) -> bool:
        """Case-insensitive duplicate check within one user's tags."""
        query = select(expense_entry_tags.c.id).where(
            expense_entry_tags.c.user_id == uuid.UUID(user_id),
            func.lower(expense_entry_tags.c.name) == name.lower(),
        )
        if exclude_tag_id is not None:
            query = query.where(expense_entry_tags.c.id != uuid.UUID(exclude_tag_id))
        return (await self.db.execute(query.limit(1))).first() is not None

    async def create_tag(self, user_id: str, tag_data: EntryTagCreate) -> ExpenseEntryTagModel:
        """Create a new entry tag (name saved as 'Capitalized first letter')."""
        name = normalize_tag_name(tag_data.name)
        if not name:
            raise ValueError("Tag name cannot be empty")
        if await self._name_taken(user_id, name):
            raise ValueError(f"Tag with name '{name}' already exists")

        new_id = uuid.uuid4()
        values = {
            "id": new_id,
            "user_id": uuid.UUID(user_id),
            "name": name,
            "created_at": datetime.now(timezone.utc),
        }
        await self.db.execute(expense_entry_tags.insert().values(**values))
        await self.db.commit()

        return ExpenseEntryTagModel(**{**values, "_id": str(new_id)})

    def _counted_query(self):
        """Tags plus how many entries use each, in ONE grouped query (no N+1)."""
        return (
            select(
                *expense_entry_tags.c,
                func.count(expense_entry_tag_links.c.expense_entry_id).label("entry_count"),
            )
            .select_from(
                expense_entry_tags.outerjoin(
                    expense_entry_tag_links, expense_entry_tag_links.c.tag_id == expense_entry_tags.c.id
                )
            )
            .group_by(expense_entry_tags.c.id)
        )

    async def get_tags(self, user_id: str) -> list[ExpenseEntryTagModel]:
        """Get all tags for a user with usage counts, sorted by name (case-insensitive)."""
        result = await self.db.execute(
            self._counted_query()
            .where(expense_entry_tags.c.user_id == uuid.UUID(user_id))
            .order_by(func.lower(expense_entry_tags.c.name))
        )
        return [self._to_model(row, row["entry_count"]) for row in result.mappings().all()]

    async def get_tag_by_id(self, user_id: str, tag_id: str) -> ExpenseEntryTagModel | None:
        """Get a specific tag (with its usage count)."""
        if not is_valid_id(tag_id):
            return None

        result = await self.db.execute(
            self._counted_query().where(
                expense_entry_tags.c.id == uuid.UUID(tag_id), expense_entry_tags.c.user_id == uuid.UUID(user_id)
            )
        )
        row = result.mappings().first()
        return self._to_model(row, row["entry_count"]) if row else None

    async def get_tag_by_name(self, user_id: str, name: str) -> ExpenseEntryTagModel | None:
        """Find one of the user's tags by name, ignoring case and extra spaces.
        Shared by the MCP and chatbot tools, which refer to tags by name."""
        wanted = " ".join(name.split()).lower()
        if not wanted:
            return None
        result = await self.db.execute(
            self._counted_query().where(
                expense_entry_tags.c.user_id == uuid.UUID(user_id), func.lower(expense_entry_tags.c.name) == wanted
            )
        )
        row = result.mappings().first()
        return self._to_model(row, row["entry_count"]) if row else None

    async def update_tag(self, user_id: str, tag_id: str, tag_data: EntryTagUpdate) -> ExpenseEntryTagModel | None:
        """Rename a tag. Returns None if it does not exist (or is not the
        user's); raises ValueError if the new name clashes with another tag."""
        if not is_valid_id(tag_id):
            return None

        name = normalize_tag_name(tag_data.name)
        if not name:
            raise ValueError("Tag name cannot be empty")
        if await self._name_taken(user_id, name, exclude_tag_id=tag_id):
            raise ValueError(f"Tag with name '{name}' already exists")

        result = await self.db.execute(
            expense_entry_tags.update()
            .where(expense_entry_tags.c.id == uuid.UUID(tag_id), expense_entry_tags.c.user_id == uuid.UUID(user_id))
            .values(name=name)
            .returning(expense_entry_tags.c.id)
        )
        found = result.first()
        await self.db.commit()
        if not found:
            return None
        return await self.get_tag_by_id(user_id, tag_id)

    async def delete_tag(self, user_id: str, tag_id: str) -> int | None:
        """Delete a tag in one transaction: the tag row (its links cascade, so
        entries just lose the tag) and its id in the user's
        `default_excluded_tags` (that array has no foreign key).

        Returns how many entries lost the tag, or None if the tag was not
        found. Expenses and entries themselves are never deleted."""
        if not is_valid_id(tag_id):
            return None

        tag_uuid, user_uuid = uuid.UUID(tag_id), uuid.UUID(user_id)
        owned = (
            await self.db.execute(
                select(expense_entry_tags.c.id).where(
                    expense_entry_tags.c.id == tag_uuid, expense_entry_tags.c.user_id == user_uuid
                )
            )
        ).first()
        if not owned:
            return None

        entries_untagged = (
            await self.db.execute(
                select(func.count())
                .select_from(expense_entry_tag_links)
                .where(expense_entry_tag_links.c.tag_id == tag_uuid)
            )
        ).scalar_one()

        await self.db.execute(
            update(user_preferences)
            .where(user_preferences.c.user_id == user_uuid)
            .values(default_excluded_tags=func.array_remove(user_preferences.c.default_excluded_tags, tag_uuid))
        )
        await self.db.execute(
            expense_entry_tags.delete().where(
                expense_entry_tags.c.id == tag_uuid, expense_entry_tags.c.user_id == user_uuid
            )
        )
        await self.db.commit()
        return entries_untagged
