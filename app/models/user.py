import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class UserModel(BaseModel):
    """User DB model."""

    id: str | None = Field(default=None, alias="_id")
    username: str = Field(..., min_length=7, max_length=20)
    email: str
    password: str
    is_subscribed_to_emails: bool = True
    is_admin: bool = False
    chatbot_enabled: bool = False
    is_disabled: bool = False
    email_verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("id", mode="before")
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
                "username": "johndoe",
                "email": "john@example.com",
                "is_subscribed_to_emails": True,
            }
        },
    }
