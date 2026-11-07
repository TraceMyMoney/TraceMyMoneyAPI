import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import user_preferences
from app.models.user_preference import UserPreferenceModel
from app.schemas.user_preference import UserPreferenceUpdate


class UserPreferenceService:
    """Service for user preference-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_preferences(self, user_id: str) -> UserPreferenceModel:
        """Get user preferences or create default if doesn't exist."""
        result = await self.db.execute(select(user_preferences).where(user_preferences.c.user_id == uuid.UUID(user_id)))
        row = result.mappings().first()

        if not row:
            now = datetime.now(timezone.utc)
            values = {
                "id": uuid.uuid4(),
                "user_id": uuid.UUID(user_id),
                "page_size": 5,
                "is_dark_mode": False,
                "privacy_mode_enabled": False,
                "banks_display_order": [],
                "created_at": now,
                "updated_at": now,
            }
            insert_result = await self.db.execute(
                user_preferences.insert().values(**values).returning(*user_preferences.c)
            )
            row = insert_result.mappings().first()
            await self.db.commit()

        return UserPreferenceModel(**{**row, "_id": str(row["id"])})

    async def update_preferences(self, user_id: str, pref_data: UserPreferenceUpdate) -> UserPreferenceModel:
        """Update user preferences (upserts, defaulting any unset column per the table schema)."""
        update_data = pref_data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now(timezone.utc)
        for key in ("banks_display_order", "default_excluded_tags"):
            if update_data.get(key) is not None:
                update_data[key] = [uuid.UUID(str(i)) for i in update_data[key]]
            elif key in update_data:
                del update_data[key]  # explicit null = leave unchanged

        uid = uuid.UUID(user_id)
        insert_values = {
            "id": uuid.uuid4(),
            "user_id": uid,
            **update_data,
        }

        stmt = pg_insert(user_preferences).values(**insert_values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[user_preferences.c.user_id],
            set_={k: v for k, v in update_data.items()},
        ).returning(*user_preferences.c)

        result = await self.db.execute(stmt)
        row = result.mappings().first()
        await self.db.commit()

        if row:
            return UserPreferenceModel(**{**row, "_id": str(row["id"])})

        return await self.get_or_create_preferences(user_id)
