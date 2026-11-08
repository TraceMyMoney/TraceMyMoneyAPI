from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ExpenseEntryType(str, Enum):
    """Expense entry types."""

    EXPENSE = "expense"
    TOPUP = "topup"  # Negative amount (money added back)


class ExpenseEntryModel(BaseModel):
    """Expense entry DB model."""

    ee_id: str | int = Field(..., description="Unique entry ID")
    amount: float = Field(..., description="Amount (positive for expense, negative for topup)")
    description: str = Field(default="", max_length=200)
    entry_tags: list[str] = Field(default_factory=list, description="List of tag IDs")
    expense_entry_type: ExpenseEntryType = ExpenseEntryType.EXPENSE
    created_at: datetime | None = Field(default_factory=datetime.utcnow)

    model_config = {
        "json_schema_extra": {
            "example": {
                "ee_id": "ee_123456",
                "amount": 50.00,
                "description": "Grocery shopping",
                "entry_tags": ["tag1", "tag2"],
                "expense_entry_type": "expense",
            }
        }
    }
