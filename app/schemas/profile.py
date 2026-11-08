from pydantic import BaseModel, EmailStr, Field


class ProfileUpdate(BaseModel):
    username: str | None = Field(None, min_length=7, max_length=20)
    email: EmailStr | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
