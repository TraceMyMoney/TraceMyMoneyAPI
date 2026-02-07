from typing import Optional
from pydantic import BaseModel, Field


class UserPreferenceBase(BaseModel):
    """Base user preference schema."""

    page_size: int = Field(default=5, ge=1, le=100)
    is_dark_mode: bool = False
    privacy_mode_enabled: bool = False


class UserPreferenceCreate(UserPreferenceBase):
    """Schema for creating user preferences."""

    pass


class UserPreferenceUpdate(BaseModel):
    """Schema for updating user preferences."""

    page_size: Optional[int] = Field(None, ge=1, le=100)
    is_dark_mode: Optional[bool] = None
    privacy_mode_enabled: Optional[bool] = None


class UserPreferenceResponse(UserPreferenceBase):
    """User preference schema for API responses."""

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {"page_size": 10, "is_dark_mode": True, "privacy_mode_enabled": False}
        },
    }
