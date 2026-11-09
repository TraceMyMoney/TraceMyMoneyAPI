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


class EmailRequest(BaseModel):
    """Body for resend-verification and forgot-password."""

    email: str


class TokenRequest(BaseModel):
    """Body for verify-email: the opaque token from the emailed link."""

    token: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str
