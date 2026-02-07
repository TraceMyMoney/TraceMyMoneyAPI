from typing import List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.models.bank import BankModel
from app.schemas.bank import BankCreate, BankUpdate


class BankService:
    """Service for bank-related business logic."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.banks
        self.expenses_collection = db.expenses

    async def create_bank(self, user_id: str, bank_data: BankCreate) -> BankModel:
        """Create a new bank."""
        bank_dict = bank_data.model_dump()
        bank_dict["user_id"] = user_id

        # Handle created_at if provided
        if bank_data.created_at:
            try:
                from app.utils.date_utils import parse_date_string

                bank_dict["created_at"] = parse_date_string(bank_data.created_at)
            except:
                bank_dict["created_at"] = datetime.utcnow()
        else:
            bank_dict["created_at"] = datetime.utcnow()

        bank_dict["updated_at"] = datetime.utcnow()

        result = await self.collection.insert_one(bank_dict)
        bank_dict["_id"] = str(result.inserted_id)
        bank_dict["user_id"] = user_id

        return BankModel(**bank_dict)

    async def get_banks(
        self, user_id: str, bank_id: Optional[str] = None, name: Optional[str] = None
    ) -> List[BankModel]:
        """Get banks for a user with optional filters."""
        query = {"user_id": user_id}

        if bank_id and ObjectId.is_valid(bank_id):
            query["_id"] = ObjectId(bank_id)

        if name:
            query["name"] = name

        cursor = self.collection.find(query)
        banks = await cursor.to_list(length=None)

        # Convert ObjectIds to strings
        for bank in banks:
            bank["_id"] = str(bank["_id"])

        return [BankModel(**bank) for bank in banks]

    async def get_bank_by_id(self, user_id: str, bank_id: str) -> Optional[BankModel]:
        """Get a specific bank."""
        if not ObjectId.is_valid(bank_id):
            return None

        bank = await self.collection.find_one({"_id": ObjectId(bank_id), "user_id": user_id})
        if bank:
            bank["_id"] = str(bank["_id"])
            return BankModel(**bank)
        return None

    async def update_bank(self, user_id: str, bank_id: str, bank_data: BankUpdate) -> Optional[BankModel]:
        """Update a bank."""
        if not ObjectId.is_valid(bank_id):
            return None

        update_data = bank_data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(bank_id), "user_id": user_id}, {"$set": update_data}, return_document=True
        )

        if result:
            result["_id"] = str(result["_id"])
            return BankModel(**result)
        return None

    async def delete_bank(self, user_id: str, bank_id: str) -> bool:
        """Delete a bank and all associated expenses."""
        if not ObjectId.is_valid(bank_id):
            return False

        # First check if bank exists
        bank = await self.collection.find_one({"_id": ObjectId(bank_id), "user_id": user_id})
        if not bank:
            return False

        # Delete all expenses associated with this bank
        await self.expenses_collection.delete_many({"bank_id": bank_id, "user_id": user_id})

        # Delete the bank
        result = await self.collection.delete_one({"_id": ObjectId(bank_id), "user_id": user_id})
        return result.deleted_count > 0

    async def update_bank_balance(
        self, user_id: str, bank_id: str, amount_change: float, disbursed_change: float
    ) -> Optional[BankModel]:
        """Update bank balance and total disbursed."""
        if not ObjectId.is_valid(bank_id):
            return None

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(bank_id), "user_id": user_id},
            {
                "$inc": {"current_balance": amount_change, "total_disbursed_till_now": disbursed_change},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=True,
        )

        if result:
            result["_id"] = str(result["_id"])
            return BankModel(**result)
        return None
