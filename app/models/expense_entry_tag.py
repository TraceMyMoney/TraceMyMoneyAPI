from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId


class ExpenseEntryTagModel(BaseModel):
    """MongoDB Expense Entry Tag Document Model."""

    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    name: str = Field(..., max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, v):
        """Convert ObjectId to string if needed."""
        if isinstance(v, ObjectId):
            return str(v)
        return v

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "name": "Groceries",
            }
        },
    }
