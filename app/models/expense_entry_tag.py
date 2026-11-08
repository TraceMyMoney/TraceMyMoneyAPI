import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ExpenseEntryTagModel(BaseModel):
    """Expense entry tag DB model."""

    id: str | None = Field(default=None, alias="_id")
    user_id: str
    name: str = Field(..., max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)

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
                "name": "Groceries",
            }
        },
    }
