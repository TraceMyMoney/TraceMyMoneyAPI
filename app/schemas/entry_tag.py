from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EntryTagBase(BaseModel):
    """Base entry tag schema."""

    name: str = Field(..., max_length=50)


class EntryTagCreate(EntryTagBase):
    """Schema for creating an entry tag."""

    pass


class EntryTagUpdate(BaseModel):
    """Schema for updating an entry tag."""

    name: Optional[str] = Field(None, max_length=50)


class EntryTagResponse(EntryTagBase):
    """Entry tag schema for API responses."""

    id: str = Field(..., alias="_id")
    created_at: datetime

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }
