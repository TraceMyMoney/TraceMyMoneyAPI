from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.expense_entry import ExpenseEntryCreate, ExpenseEntryResponse


class ExpenseBase(BaseModel):
    """Base expense schema."""

    bank_id: str


class ExpenseCreate(ExpenseBase):
    """Schema for creating an expense."""

    expenses: List[ExpenseEntryCreate] = Field(..., min_length=1)
    created_at: Optional[str] = None  # Optional date string from client

    model_config = {
        "json_schema_extra": {
            "example": {
                "bank_id": "507f1f77bcf86cd799439011",
                "expenses": [
                    {
                        "amount": 50.00,
                        "description": "Grocery shopping",
                        "selected_tags": ["tag1", "tag2"],
                        "type": "expense",
                    }
                ],
                "created_at": "7/2/2026 00:00",
            }
        }
    }


class ExpenseUpdate(BaseModel):
    """Schema for updating an expense."""

    bank_id: Optional[str] = None
    expenses: Optional[List[ExpenseEntryCreate]] = None


class ExpenseResponse(BaseModel):
    """Expense schema for API responses."""

    id: str = Field(..., alias="_id")
    user_id: str
    bank_name: str
    day: str
    expenses: List[ExpenseEntryResponse]
    expense_total: float
    topup_expense_total: Optional[float] = 0.0 
    remaining_amount_till_now: float
    created_at: datetime

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }


class ExpenseListResponse(BaseModel):
    """Response for expense list with totals."""

    expenses: List[ExpenseResponse]
    total_expenses: int
    non_topup_total: float
    topup_total: float
