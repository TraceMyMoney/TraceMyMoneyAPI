import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.tables import banks
from app.models.bank import BankModel
from app.schemas.bank import BankCreate, BankUpdate
from app.services.user_service import is_valid_id


class BankService:
    """Service for bank-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_bank(self, user_id: str, bank_data: BankCreate) -> BankModel:
        """Create a new bank."""
        bank_dict = bank_data.model_dump(exclude={"created_at"})

        if bank_data.created_at:
            try:
                from app.utils.date_utils import parse_date_string, to_utc_aware

                created_at = to_utc_aware(parse_date_string(bank_data.created_at))
            except Exception:
                created_at = datetime.now(timezone.utc)
        else:
            created_at = datetime.now(timezone.utc)

        new_id = uuid.uuid4()
        values = {
            "id": new_id,
            "user_id": uuid.UUID(user_id),
            **bank_dict,
            "created_at": created_at,
            "updated_at": datetime.now(timezone.utc),
        }
        await self.db.execute(banks.insert().values(**values))
        await self.db.commit()

        return BankModel(**{**values, "_id": str(new_id), "user_id": user_id})

    async def get_banks(
        self, user_id: str, bank_id: Optional[str] = None, name: Optional[str] = None
    ) -> List[BankModel]:
        """Get banks for a user with optional filters."""
        query = select(banks).where(banks.c.user_id == uuid.UUID(user_id))

        if bank_id and is_valid_id(bank_id):
            query = query.where(banks.c.id == uuid.UUID(bank_id))

        if name:
            query = query.where(banks.c.name == name)

        result = await self.db.execute(query)
        rows = result.mappings().all()

        return [BankModel(**{**row, "_id": str(row["id"]), "user_id": str(row["user_id"])}) for row in rows]

    async def get_bank_by_id(self, user_id: str, bank_id: str) -> Optional[BankModel]:
        """Get a specific bank."""
        if not is_valid_id(bank_id):
            return None

        result = await self.db.execute(
            select(banks).where(banks.c.id == uuid.UUID(bank_id), banks.c.user_id == uuid.UUID(user_id))
        )
        row = result.mappings().first()
        if row:
            return BankModel(**{**row, "_id": str(row["id"]), "user_id": str(row["user_id"])})
        return None

    async def update_bank(self, user_id: str, bank_id: str, bank_data: BankUpdate) -> Optional[BankModel]:
        """Update a bank."""
        if not is_valid_id(bank_id):
            return None

        update_data = bank_data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now(timezone.utc)

        result = await self.db.execute(
            banks.update()
            .where(banks.c.id == uuid.UUID(bank_id), banks.c.user_id == uuid.UUID(user_id))
            .values(**update_data)
            .returning(*banks.c)
        )
        row = result.mappings().first()
        await self.db.commit()

        if row:
            return BankModel(**{**row, "_id": str(row["id"]), "user_id": str(row["user_id"])})
        return None

    async def delete_bank(self, user_id: str, bank_id: str) -> bool:
        """
        Delete a bank and all associated expenses.

        Expense deletion is now handled by `ON DELETE CASCADE` on
        expenses.bank_id (see alembic/versions/330acedcd320_initial_schema.py),
        fixing the Mongo-era bug where BankService deleted from the wrong
        collection (`db.expenses`) and orphaned expenses (PLAN.md bug #2).
        """
        if not is_valid_id(bank_id):
            return False

        result = await self.db.execute(
            banks.delete().where(banks.c.id == uuid.UUID(bank_id), banks.c.user_id == uuid.UUID(user_id))
        )
        await self.db.commit()
        return result.rowcount > 0

    async def update_bank_balance(
        self, user_id: str, bank_id: str, amount_change: float, disbursed_change: float
    ) -> Optional[BankModel]:
        """Update bank balance and total disbursed."""
        if not is_valid_id(bank_id):
            return None

        result = await self.db.execute(
            banks.update()
            .where(banks.c.id == uuid.UUID(bank_id), banks.c.user_id == uuid.UUID(user_id))
            .values(
                current_balance=banks.c.current_balance + amount_change,
                total_disbursed_till_now=banks.c.total_disbursed_till_now + disbursed_change,
                updated_at=datetime.now(timezone.utc),
            )
            .returning(*banks.c)
        )
        row = result.mappings().first()
        await self.db.commit()

        if row:
            return BankModel(**{**row, "_id": str(row["id"]), "user_id": str(row["user_id"])})
        return None
