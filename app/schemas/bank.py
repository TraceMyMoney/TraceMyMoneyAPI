from datetime import datetime

from pydantic import BaseModel, Field


class BankBase(BaseModel):
    """Base bank schema."""

    name: str = Field(..., max_length=20)


class BankCreate(BankBase):
    """Schema for creating a bank."""

    initial_balance: float = Field(..., gt=0)
    current_balance: float = Field(..., gt=0)
    total_disbursed_till_now: float = 0.0
    created_at: str | None = None  # Optional date string from client

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Chase Checking",
                "initial_balance": 5000.00,
                "current_balance": 5000.00,
                "total_disbursed_till_now": 0.0,
            }
        }
    }


class BankUpdate(BaseModel):
    """Schema for updating a bank."""

    name: str | None = Field(None, max_length=20)
    initial_balance: float | None = Field(None, gt=0)
    current_balance: float | None = None
    total_disbursed_till_now: float | None = None


class BankResponse(BankBase):
    """Bank schema for API responses."""

    id: str = Field(..., alias="_id")
    initial_balance: float
    current_balance: float
    total_disbursed_till_now: float
    created_at: datetime

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }
