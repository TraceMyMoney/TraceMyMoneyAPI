from typing import Optional
from pydantic import BaseModel, Field, model_validator


class Token(BaseModel):
    """JWT token response schema - matches Flask response format."""

    token: str
    refresh_token: str
    status_code: int = 201


class TokenPayload(BaseModel):
    """JWT token payload schema."""

    user_id: Optional[str] = None
    user_name: Optional[str] = None
    exp: Optional[int] = None


class LoginRequest(BaseModel):
    """Login request schema."""

    username: str
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "username": "johndoe",
                "password": "secretpassword123",
            }
        }
    }


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None
    token: Optional[str] = Field(default=None, description="Alias for refresh_token")

    @model_validator(mode="after")
    def resolve_refresh_token(self):
        refresh_token = self.refresh_token or self.token
        if not refresh_token:
            raise ValueError("refresh_token is required")
        self.refresh_token = refresh_token
        return self

    model_config = {"populate_by_name": True}
