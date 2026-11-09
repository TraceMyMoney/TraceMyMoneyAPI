from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def normalize_tag_name(name: str) -> str:
    """The one place that decides how a tag name is saved: trim, collapse
    repeated whitespace, upper-case ONLY the first letter. The rest stays as
    typed, so 'food' -> 'Food', 'rent  and bills' -> 'Rent and bills' and
    'EMI' stays 'EMI'."""
    cleaned = " ".join(name.split())
    return cleaned[:1].upper() + cleaned[1:]


class EntryTagBase(BaseModel):
    """Base entry tag schema."""

    name: str = Field(..., min_length=1, max_length=50)

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, v):
        return normalize_tag_name(v) if isinstance(v, str) else v


class EntryTagCreate(EntryTagBase):
    """Schema for creating an entry tag."""

    pass


class EntryTagUpdate(EntryTagBase):
    """Schema for renaming an entry tag (the name is required)."""

    pass


class EntryTagResponse(EntryTagBase):
    """Entry tag schema for API responses."""

    id: str = Field(..., alias="_id")
    created_at: datetime
    entry_count: int = 0

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }
