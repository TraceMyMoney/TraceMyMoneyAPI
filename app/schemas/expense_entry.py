from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.expense_entry import ExpenseEntryType


class ExpenseEntryCreate(BaseModel):
    """Schema for creating an expense entry."""

    amount: float
    description: str = Field(default="", max_length=200)
    selected_tags: List[str] = Field(default_factory=list)
    type: ExpenseEntryType = ExpenseEntryType.EXPENSE

    model_config = {
        "json_schema_extra": {
            "example": {
                "amount": 50.00,
                "description": "Grocery shopping",
                "selected_tags": ["groceries", "food"],
                "type": "expense",
            }
        }
    }


class ExpenseEntryUpdate(BaseModel):
    """Schema for updating an expense entry."""

    expense_id: str
    entry_id: str
    updated_description: Optional[str] = Field(None, max_length=200)
    selected_tags: Optional[List[str]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "expense_id": "507f1f77bcf86cd799439011",
                "entry_id": "ee_123456",
                "updated_description": "Updated description",
                "selected_tags": ["tag1", "tag2"],
            }
        }
    }


class ExpenseEntryResponse(BaseModel):
    """Expense entry schema for API responses."""

    ee_id: str
    amount: float
    description: str
    entry_tags: List[str]
    expense_entry_type: ExpenseEntryType
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class ExpenseEntryAddRequest(BaseModel):
    """Request to add expense entries to an existing expense."""

    entries: List[ExpenseEntryCreate]
