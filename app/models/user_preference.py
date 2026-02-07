from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId


class UserPreferenceModel(BaseModel):
    """MongoDB User Preference Document Model."""

    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    page_size: int = Field(default=5, ge=1, le=100)
    is_dark_mode: bool = False
    privacy_mode_enabled: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

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
                "page_size": 10,
                "is_dark_mode": True,
                "privacy_mode_enabled": False,
            }
        },
    }
