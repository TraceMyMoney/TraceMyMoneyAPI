from pydantic import BaseModel


class Token(BaseModel):
    """JWT token response schema - matches Flask response format."""

    token: str
    refresh_token: str | None = None
    status_code: int = 201


class RefreshRequest(BaseModel):
    """Refresh request schema."""

    refresh_token: str


class TokenPayload(BaseModel):
    """JWT token payload schema."""

    user_id: str | None = None
    user_name: str | None = None
    exp: int | None = None


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
