import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class UserPreferenceModel(BaseModel):
    """User preference DB model."""

    id: str | None = Field(default=None, alias="_id")
    user_id: str
    page_size: int = Field(default=5, ge=1, le=100)
    is_dark_mode: bool = False
    privacy_mode_enabled: bool | None = None
    banks_display_order: list[str] = Field(default_factory=list)
    default_excluded_tags: list[str] = Field(default_factory=list)
    daily_expense_limit: Decimal | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    @field_validator("banks_display_order", "default_excluded_tags", mode="before")
    @classmethod
    def convert_bank_ids_to_str(cls, v):
        """Convert a list of UUID (Postgres array column) to strings."""
        if v is None:
            return []
        return [str(item) if isinstance(item, uuid.UUID) else item for item in v]

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "page_size": 10,
                "is_dark_mode": True,
                "privacy_mode_enabled": False,
            }
        },
    }
