from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId


class UserModel(BaseModel):
    """MongoDB User Document Model."""

    id: Optional[str] = Field(default=None, alias="_id")
    username: str = Field(..., min_length=7, max_length=20)
    email: str
    password: str
    is_subscribed_to_emails: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("id", mode="before")
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
                "username": "johndoe",
                "email": "john@example.com",
                "is_subscribed_to_emails": True,
            }
        },
    }
