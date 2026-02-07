from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    username: str = Field(..., min_length=7, max_length=20)


class UserCreate(UserBase):
    """Schema for creating a user (registration)."""

    password: str = Field(..., min_length=8)
    is_subscribed_to_emails: Optional[bool] = True


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=7, max_length=20)
    password: Optional[str] = Field(None, min_length=8)
    is_subscribed_to_emails: Optional[bool] = None


class UserResponse(UserBase):
    """User schema for API responses."""

    id: str = Field(..., alias="_id")
    is_subscribed_to_emails: bool
    created_at: datetime

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }


class UserInDB(UserBase):
    """User schema as stored in database."""

    id: str = Field(..., alias="_id")
    hashed_password: str
    is_subscribed_to_emails: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "populate_by_name": True,
    }
