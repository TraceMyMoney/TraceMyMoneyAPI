from typing import List, Optional, Tuple
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
import uuid
from app.models.expense import ExpenseModel
from app.models.expense_entry import ExpenseEntryModel
from app.schemas.expense import ExpenseCreate
from app.schemas.expense_entry import ExpenseEntryCreate, ExpenseEntryUpdate
from app.schemas.common import AdvancedSearchParams
from app.utils.date_utils import parse_date_string


class ExpenseService:
    """Service for expense-related business logic."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.expense
        self.banks_collection = db.bank
        self.tags_collection = db.expense_entry_tag

    async def create_expense(self, user_id: str, expense_data: ExpenseCreate) -> ExpenseModel:
        """Create a new expense with entries."""
        # Get bank details
        bank = await self.banks_collection.find_one({"_id": ObjectId(expense_data.bank_id)})
        if not bank:
            raise ValueError("Bank not found for the corresponding id")

        # Parse created_at if provided
        if expense_data.created_at:
            created_at = parse_date_string(expense_data.created_at)
        else:
            created_at = datetime.utcnow()

        # Check if expense already exists for this date
        existing = await self.collection.find_one(
            {"bank": ObjectId(expense_data.bank_id), "user_id": ObjectId(user_id), "created_at": created_at}
        )

        if existing:
            raise ValueError("You cannot replicate the expense for the same day")

        # Create expense entries
        entries = []
        total_amount = 0

        for entry_data in expense_data.expenses:
            ee_id = f"ee_{uuid.uuid4().hex[:12]}"
            entry = ExpenseEntryModel(
                ee_id=ee_id,
                amount=entry_data.amount,
                description=entry_data.description,
                entry_tags=entry_data.entry_tags,
                expense_entry_type=entry_data.type,
                created_at=created_at,
            )
            entries.append(entry)
            total_amount += entry.amount

        # Get current bank balance for remaining_amount calculation
        remaining_balance = bank.get("current_balance", 0) - total_amount

        # Create expense document
        expense_dict = {
            "user_id": ObjectId(user_id),
            "bank": ObjectId(expense_data.bank_id),
            "bank_name": bank.get("name", ""),
            "day": created_at.strftime("%A"),  # Day of week
            "expenses": [entry.model_dump() for entry in entries],
            "expense_total": total_amount,
            "remaining_amount_till_now": remaining_balance,
            "created_at": created_at,
            "updated_at": datetime.utcnow(),
        }

        result = await self.collection.insert_one(expense_dict)
        expense_dict["_id"] = str(result.inserted_id)

        # Update bank balance
        await self.banks_collection.update_one(
            {"_id": ObjectId(expense_data.bank_id)},
            {
                "$inc": {"current_balance": -total_amount, "total_disbursed_till_now": total_amount},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )

        return ExpenseModel(**expense_dict)

    async def get_expenses(
        self, user_id: str, params: AdvancedSearchParams
    ) -> Tuple[List[dict], int, float, float]:
        """
        Get expenses with advanced search and pagination.
        Returns: (expenses, total_count, non_topup_total, topup_total)
        """
        # Build match query
        match_conditions = [{"user_id": ObjectId(user_id)}]

        if params.advanced_search:
            # Advanced search filters
            if params.search_by_tags:
                match_conditions.append({"expenses.entry_tags": {"$in": params.search_by_tags}})

            if params.search_by_keyword:
                match_conditions.append(
                    {"expenses.description": {"$regex": params.search_by_keyword, "$options": "i"}}
                )

            if params.search_by_bank_ids:
                bank_ids = [ObjectId(bid) for bid in params.search_by_bank_ids if ObjectId.is_valid(bid)]
                match_conditions.append({"bank": {"$in": bank_ids}})

            if params.search_by_daterange:
                date_condition = {
                    "created_at": {"$gte": parse_date_string(params.search_by_daterange.start_date)}
                }
                if params.search_by_daterange.end_date:
                    date_condition["created_at"]["$lte"] = parse_date_string(
                        params.search_by_daterange.end_date
                    )
                match_conditions.append(date_condition)
        else:
            # Simple bank filter
            if params.bank_id and ObjectId.is_valid(params.bank_id):
                match_conditions.append({"bank": ObjectId(params.bank_id)})

        # Build aggregation pipeline
        match_query = {f"${params.operator}": match_conditions}

        pipeline = [
            {"$match": match_query},
            {"$unwind": "$expenses"},
            {"$match": match_query},  # Match again after unwind
            {
                "$group": {
                    "_id": "$_id",
                    "id": {"$first": "$_id"},
                    "created_at": {"$first": "$created_at"},
                    "day": {"$first": "$day"},
                    "expense_total": {
                        "$sum": {"$cond": [{"$gt": ["$expenses.amount", 0]}, "$expenses.amount", 0]}
                    },
                    "topup_expense_total": {
                        "$sum": {"$cond": [{"$lt": ["$expenses.amount", 0]}, "$expenses.amount", 0]}
                    },
                    "remaining_amount_till_now": {"$first": "$remaining_amount_till_now"},
                    "user_id": {"$first": "$user_id"},
                    "bank_name": {"$first": "$bank_name"},
                    "expenses": {"$push": "$expenses"},
                }
            },
            {"$sort": {"created_at": -1}},
        ]

        # Execute aggregation
        cursor = self.collection.aggregate(pipeline)
        all_expenses = await cursor.to_list(length=None)

        # Calculate totals
        total_count = len(all_expenses)
        non_topup_total = sum(exp["expense_total"] for exp in all_expenses)
        topup_total = sum(exp["topup_expense_total"] for exp in all_expenses)

        # Pagination
        skip = (params.page_number - 1) * params.per_page
        paginated_expenses = all_expenses[skip : skip + params.per_page]

        # Convert ObjectIds to strings
        for expense in paginated_expenses:
            expense["_id"] = str(expense["_id"])
            expense["id"] = str(expense["id"])

        return paginated_expenses, total_count, non_topup_total, topup_total

    async def get_expense_by_id(self, user_id: str, expense_id: str) -> Optional[ExpenseModel]:
        """Get a single expense by ID."""
        if not ObjectId.is_valid(expense_id):
            return None

        expense = await self.collection.find_one({"_id": ObjectId(expense_id), "user_id": user_id})
        if expense:
            expense["_id"] = str(expense["_id"])
            return ExpenseModel(**expense)
        return None

    async def add_expense_entries(
        self, user_id: str, expense_id: str, entries: List[ExpenseEntryCreate]
    ) -> Optional[ExpenseModel]:
        """Add new entries to an existing expense."""
        if not ObjectId.is_valid(expense_id):
            return None

        expense = await self.collection.find_one(
            {"_id": ObjectId(expense_id), "user_id": ObjectId(user_id)}
        )
        if not expense:
            return None

        # Create new entries
        new_entries = []
        total_added = 0

        for entry_data in entries:
            ee_id = f"ee_{uuid.uuid4().hex[:12]}"
            entry = ExpenseEntryModel(
                ee_id=ee_id,
                amount=entry_data.amount,
                description=entry_data.description,
                entry_tags=entry_data.entry_tags,
                expense_entry_type=entry_data.type,
                created_at=expense.get("created_at", datetime.utcnow()),
            )
            new_entries.append(entry.model_dump())
            total_added += entry.amount

        remaining_balance = expense.get("remaining_amount_till_now", 0) - total_added

        # Update expense
        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(expense_id), "user_id": ObjectId(user_id)},
            {
                "$push": {"expenses": {"$each": new_entries}},
                "$inc": {"expense_total": total_added},
                "$set": {"updated_at": datetime.utcnow(), "remaining_amount_till_now": remaining_balance},
            },
            return_document=True,
        )

        if result:
            # Update bank balance
            await self.banks_collection.update_one(
                {"_id": ObjectId(expense.get("bank"))},
                {"$inc": {"current_balance": -total_added, "total_disbursed_till_now": total_added}},
            )

            result["_id"] = str(result["_id"])
            return ExpenseModel(**result)
        return None

    async def update_expense_entry(self, user_id: str, update_data: ExpenseEntryUpdate) -> Optional[dict]:
        """Update a specific expense entry."""
        if not ObjectId.is_valid(update_data.expense_id):
            return None

        # Build update dict
        update_dict = {}
        if update_data.updated_description is not None:
            update_dict["expenses.$.description"] = update_data.updated_description
        if update_data.entry_tags is not None:
            update_dict["expenses.$.entry_tags"] = update_data.entry_tags

        if not update_dict:
            return None

        update_dict["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {
                "_id": ObjectId(update_data.expense_id),
                "user_id": ObjectId(user_id),
                "expenses.ee_id": update_data.entry_id,
            },
            {"$set": update_dict},
            return_document=True,
        )

        if result:
            # Return the updated entry
            for entry in result.get("expenses", []):
                if entry.get("ee_id") == update_data.entry_id:
                    return {
                        "expense_id": str(result["_id"]),
                        "entry_id": update_data.entry_id,
                        "selected_tags": entry.get("entry_tags", []),
                        "description": entry.get("description", ""),
                    }
        return None

    async def delete_expense_entry(self, user_id: str, expense_id: str, entry_id: str) -> bool:
        """Delete a specific expense entry."""
        if not ObjectId.is_valid(expense_id):
            return False

        expense = await self.collection.find_one(
            {"_id": ObjectId(expense_id), "user_id": ObjectId(user_id)}
        )
        if not expense:
            return False

        entry_to_delete = None
        for entry in expense.get("expenses", []):
            if str(entry.get("ee_id")) == entry_id:
                entry_to_delete = entry
                break

        if not entry_to_delete:
            return False

        if len(expense["expenses"]) == 1:
            result = await self.collection.delete_one(
                {"_id": ObjectId(expense_id), "user_id": ObjectId(user_id)}
            )
        else:
            remaining_balance = expense.get("remaining_amount_till_now", 0) + entry_to_delete.get(
                "amount", 0
            )
            result = await self.collection.update_one(
                {"_id": ObjectId(expense_id), "user_id": ObjectId(user_id)},
                {
                    "$pull": {"expenses": {"ee_id": entry_id}},
                    "$set": {
                        "updated_at": datetime.utcnow(),
                        "remaining_amount_till_now": remaining_balance,
                    },
                },
            )

        if getattr(result, "modified_count", 0) > 0 or getattr(result, "deleted_count", 0) > 0:
            # Update bank balance if it was a positive expense
            amount = entry_to_delete.get("amount", 0)
            await self.banks_collection.update_one(
                {"_id": ObjectId(expense.get("bank"))},
                {"$inc": {"current_balance": amount, "total_disbursed_till_now": -amount}},
            )
            return True
        return False

    async def delete_expense(self, user_id: str, expense_id: str) -> bool:
        """Delete an entire expense."""
        if not ObjectId.is_valid(expense_id):
            return False

        expense = await self.collection.find_one(
            {"_id": ObjectId(expense_id), "user_id": ObjectId(user_id)}
        )
        if not expense:
            return False

        # Delete expense
        result = await self.collection.delete_one(
            {"_id": ObjectId(expense_id), "user_id": ObjectId(user_id)}
        )

        if result.deleted_count > 0:
            # Update bank balance
            expense_total = expense.get("expense_total", 0)
            await self.banks_collection.update_one(
                {"_id": ObjectId(expense.get("bank"))},
                {
                    "$inc": {
                        "current_balance": expense_total,
                        "total_disbursed_till_now": -expense_total,
                    }
                },
            )
            return True
        return False

    async def get_aggregated_data(self, user_id: str, bank_id: Optional[str] = None) -> dict:
        """Get aggregated expense data by tags (for graphs)."""
        match_query = {"user_id": user_id}
        if bank_id and ObjectId.is_valid(bank_id):
            match_query["bank_id"] = bank_id

        pipeline = [
            {"$match": match_query},
            {"$project": {"expenses.entry_tags": 1, "expenses.amount": 1}},
            {"$unwind": "$expenses"},
            {"$unwind": "$expenses.entry_tags"},
            {
                "$group": {
                    "_id": "$expenses.entry_tags",
                    "tags_wise_summation": {
                        "$sum": {"$cond": [{"$gt": ["$expenses.amount", 0]}, "$expenses.amount", 0]}
                    },
                }
            },
        ]

        cursor = self.collection.aggregate(pipeline)
        aggregated_data = await cursor.to_list(length=None)

        # Get tag names
        tag_ids = [item["_id"] for item in aggregated_data if ObjectId.is_valid(item["_id"])]
        tags_cursor = self.tags_collection.find(
            {"_id": {"$in": [ObjectId(tid) for tid in tag_ids]}, "user_id": user_id}
        )
        tags = await tags_cursor.to_list(length=None)
        tag_names = {str(tag["_id"]): tag["name"] for tag in tags}

        # Map tag names to aggregated data
        result = {}
        for item in aggregated_data:
            tag_id = item["_id"]
            result[tag_id] = {
                "tags_wise_summation": item["tags_wise_summation"],
                "tag_name": tag_names.get(tag_id, "Unknown"),
            }

        return result
