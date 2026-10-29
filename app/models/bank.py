import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class BankModel(BaseModel):
    """Bank DB model."""

    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    name: str = Field(..., max_length=20)
    initial_balance: float = Field(..., gt=0)
    current_balance: float
    total_disbursed_till_now: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "name": "Chase Checking",
                "initial_balance": 5000.00,
                "current_balance": 4500.00,
                "total_disbursed_till_now": 500.00,
            }
        },
    }
