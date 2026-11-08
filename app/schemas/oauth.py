"""Wire formats for the OAuth endpoints (RFC 7591 / RFC 8414), so field names
use underscores exactly as the spec does."""

from pydantic import BaseModel


class DCRRequest(BaseModel):
    client_name: str = "Claude"
    redirect_uris: list[str] = []
    client_uri: str | None = None

    model_config = {"extra": "ignore"}


class DCRResponse(BaseModel):
    client_id: str
    client_name: str
    redirect_uris: list[str]
    token_endpoint_auth_method: str = "none"
    grant_types: list[str] = ["authorization_code"]
    response_types: list[str] = ["code"]


class OAuthMetadata(BaseModel):
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    response_types_supported: list[str] = ["code"]
    grant_types_supported: list[str] = ["authorization_code"]
    code_challenge_methods_supported: list[str] = ["S256"]
    token_endpoint_auth_methods_supported: list[str] = ["none"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ApproveRequest(BaseModel):
    client_id: str
    redirect_uri: str
    state: str = ""
    code_challenge: str
    code_challenge_method: str = "S256"
    approve: bool = True


class AuthorizeInfo(BaseModel):
    client_name: str
    redirect_host: str


class ConnectedApp(BaseModel):
    id: str
    client_name: str
    created_at: str
    last_used_at: str
    expires_at: str


class TokenValidation(BaseModel):
    user_id: str
    username: str
    email: str
