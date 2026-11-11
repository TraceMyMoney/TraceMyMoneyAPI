from decimal import Decimal

from pydantic import BaseModel, Field

MAX_DAILY_EXPENSE_LIMIT = 10_000_000


class UserPreferenceBase(BaseModel):
    page_size: int = Field(default=5, ge=1, le=100)
    is_dark_mode: bool = False
    privacy_mode_enabled: bool = False
    banks_display_order: list[str] = Field(default_factory=list)
    default_excluded_tags: list[str] = Field(default_factory=list)


class UserPreferenceCreate(UserPreferenceBase):
    pass


class UserPreferenceUpdate(BaseModel):
    page_size: int | None = Field(None, ge=1, le=100)
    is_dark_mode: bool | None = None
    privacy_mode_enabled: bool | None = None
    banks_display_order: list[str] = Field(default_factory=list)
    default_excluded_tags: list[str] | None = None
    # Explicit null clears the limit (no limit); omitting the field leaves it unchanged.
    daily_expense_limit: Decimal | None = Field(None, gt=0, le=MAX_DAILY_EXPENSE_LIMIT, decimal_places=2)


class UserPreferenceResponse(UserPreferenceBase):
    daily_expense_limit: float | None = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {"example": {"page_size": 10, "is_dark_mode": True, "privacy_mode_enabled": False}},
    }


class UserPreferenceNoContentResponse(BaseModel):
    message: str = Field(...)
