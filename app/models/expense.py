from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId
from app.models.expense_entry import ExpenseEntryModel


class ExpenseModel(BaseModel):
    """MongoDB Expense Document Model."""

    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    bank_id: str
    bank_name: str = ""
    day: str = ""  # Day of week or date string
    expenses: List[ExpenseEntryModel] = Field(default_factory=list)
    expense_total: float = 0.0
    remaining_amount_till_now: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("id", "user_id", "bank_id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, v):
        """Convert ObjectId to string if needed."""
        if isinstance(v, ObjectId):
            return str(v)
        return v

    def calculate_totals(self):
        """Calculate expense totals from entries."""
        total = sum(entry.amount for entry in self.expenses if entry.amount > 0)
        topup_total = sum(entry.amount for entry in self.expenses if entry.amount < 0)
        self.expense_total = total
        return total, topup_total

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "bank_id": "507f1f77bcf86cd799439011",
                "bank_name": "Chase Checking",
                "day": "Monday",
                "expenses": [],
                "expense_total": 150.00,
                "remaining_amount_till_now": 4350.00,
            }
        },
    }
