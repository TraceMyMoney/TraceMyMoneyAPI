from datetime import datetime

from pydantic import BaseModel, Field

from app.models.expense_entry import ExpenseEntryType


class ExpenseEntryCreate(BaseModel):
    """Schema for creating an expense entry."""

    amount: float
    description: str = Field(default="", max_length=200)
    entry_tags: list[str] = Field(default_factory=list)
    type: ExpenseEntryType = ExpenseEntryType.EXPENSE

    model_config = {
        "json_schema_extra": {
            "example": {
                "amount": 50.00,
                "description": "Grocery shopping",
                "entry_tags": ["<tag_uuid>", "<tag_uuid>"],
                "type": "expense",
            }
        }
    }


class ExpenseEntryUpdate(BaseModel):
    """Schema for updating an expense entry."""

    expense_id: str | int
    entry_id: str | int
    updated_description: str | None = Field(None, max_length=200)
    entry_tags: list[str] | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "expense_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "entry_id": "ee_123456",
                "updated_description": "Updated description",
                "entry_tags": ["tag1", "tag2"],
            }
        }
    }


class ExpenseEntryResponse(BaseModel):
    """Expense entry schema for API responses."""

    ee_id: str | int
    amount: float
    description: str
    entry_tags: list[str] | None = None
    expense_entry_type: str | None = None
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class ExpenseEntryAddRequest(BaseModel):
    """Request to add expense entries to an existing expense."""

    entries: list[ExpenseEntryCreate]
