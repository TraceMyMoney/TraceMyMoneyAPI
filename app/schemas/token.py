from typing import Optional
from pydantic import BaseModel


class Token(BaseModel):
    """JWT token response schema - matches Flask response format."""

    token: str
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
