import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.expense_entry import ExpenseEntryCreate, ExpenseEntryResponse

DATE_TIME_FORMAT = "%d/%m/%Y %H:%M"


class ExpenseBase(BaseModel):
    """Base expense schema."""

    bank_id: str


class ExpenseCreate(ExpenseBase):
    """Schema for creating an expense."""

    expenses: list[ExpenseEntryCreate] = Field(..., min_length=1)
    created_at: str | None = None  # Optional date string from client

    model_config = {
        "json_schema_extra": {
            "example": {
                "bank_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
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

    bank_id: str | None = None
    expenses: list[ExpenseEntryCreate] | None = None


class ExpenseResponse(BaseModel):
    """Expense schema for API responses."""

    id: str = Field(..., alias="_id")
    user_id: str
    bank_name: str
    day: str
    expenses: list[ExpenseEntryResponse]
    expense_total: float
    topup_expense_total: float | None = 0.0
    remaining_amount_till_now: float
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.strftime(DATE_TIME_FORMAT)

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def convert_objectid(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }


class ExpenseListResponse(BaseModel):
    """Response for expense list with totals."""

    expenses: list[ExpenseResponse]
    total_expenses: int
    non_topup_total: float
    topup_total: float
