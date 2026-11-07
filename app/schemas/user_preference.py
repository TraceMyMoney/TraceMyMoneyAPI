from pydantic import BaseModel, Field


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


class UserPreferenceResponse(UserPreferenceBase):
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {"example": {"page_size": 10, "is_dark_mode": True, "privacy_mode_enabled": False}},
    }


class UserPreferenceNoContentResponse(BaseModel):
    message: str = Field(...)
