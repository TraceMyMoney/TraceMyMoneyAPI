import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class UserPreferenceModel(BaseModel):
    """User preference DB model."""

    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    page_size: int = Field(default=5, ge=1, le=100)
    is_dark_mode: bool = False
    privacy_mode_enabled: Optional[bool] = None
    banks_display_order: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    @field_validator("banks_display_order", mode="before")
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
