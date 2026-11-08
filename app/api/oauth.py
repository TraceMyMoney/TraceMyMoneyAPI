"""OAuth endpoints for the Claude connector.

Protocol (root paths, as the specs expect):
  GET  /.well-known/oauth-authorization-server   RFC 8414 metadata
  GET  /.well-known/oauth-protected-resource     RFC 9728 (also under /mcp/)
  POST /oauth/register                           RFC 7591 dynamic registration
  GET  /oauth/authorize                          bounces the browser to the app's approval page
  POST /oauth/token                              code (+PKCE) -> access token

Called by the app's approval page / Profile (JWT auth):
  GET  /oauth/authorize/info                     validate the request, name the client
  POST /oauth/authorize/decision                 approve or deny -> where to send the browser
  GET  /oauth/connections, DELETE /oauth/connections/{id}

Called by the MCP server:
  GET  /oauth/validate                           is this Bearer token live?
"""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.config import settings
from app.schemas.oauth import (
    ApproveRequest,
    AuthorizeInfo,
    ConnectedApp,
    DCRRequest,
    DCRResponse,
    OAuthMetadata,
    TokenResponse,
    TokenValidation,
)
from app.services.oauth_service import OAuthError, OAuthService

router = APIRouter(tags=["oauth"])


def get_oauth_service(db: AsyncSession = Depends(get_db)) -> OAuthService:
    return OAuthService(db)


OAuthServiceDep = Annotated[OAuthService, Depends(get_oauth_service)]


def _bad_request(e: OAuthError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/.well-known/oauth-authorization-server")
async def oauth_metadata() -> OAuthMetadata:
    base = settings.API_BASE_URL
    return OAuthMetadata(
        issuer=base,
        authorization_endpoint=f"{base}/oauth/authorize",
        token_endpoint=f"{base}/oauth/token",
        registration_endpoint=f"{base}/oauth/register",
    )


@router.get("/.well-known/oauth-protected-resource")
@router.get("/mcp/.well-known/oauth-protected-resource")
async def protected_resource_metadata():
    base = settings.API_BASE_URL
    return {"resource": f"{base}/mcp", "authorization_servers": [base]}


@router.post("/oauth/register", response_model=DCRResponse, status_code=201)
async def register_client(payload: DCRRequest, oauth: OAuthServiceDep):
    try:
        client = await oauth.register_client(payload.client_name, payload.redirect_uris, payload.client_uri)
    except OAuthError as e:
        # RFC 7591 error shape
        return JSONResponse({"error": "invalid_redirect_uri", "error_description": str(e)}, status_code=400)
    return DCRResponse(**client)


@router.get("/oauth/authorize")
async def authorize(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: str = Query(""),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    response_type: str = Query("code"),
):
    """Claude sends the browser here. The approval page lives in the app (it
    holds the user's session), so forward every parameter to it."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge or "",
        "code_challenge_method": code_challenge_method or "",
        "response_type": response_type,
    }
    return RedirectResponse(f"{settings.FRONTEND_BASE_URL}/oauth/authorize?{urlencode(params)}", status_code=302)


@router.get("/oauth/authorize/info", response_model=AuthorizeInfo)
async def authorize_info(
    current_user: CurrentUser,
    oauth: OAuthServiceDep,
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
):
    try:
        return AuthorizeInfo(**await oauth.authorize_info(client_id, redirect_uri, code_challenge, code_challenge_method))
    except OAuthError as e:
        raise _bad_request(e)


@router.post("/oauth/authorize/decision")
async def authorize_decision(payload: ApproveRequest, current_user: CurrentUser, oauth: OAuthServiceDep):
    """The signed-in user's answer. Returns {redirect_url}; the app sends the browser there."""
    try:
        await oauth.authorize_info(payload.client_id, payload.redirect_uri, payload.code_challenge, payload.code_challenge_method)
    except OAuthError as e:
        raise _bad_request(e)
    if not payload.approve:
        return {"redirect_url": oauth.deny_url(payload.redirect_uri, payload.state)}
    url = await oauth.approve(current_user.id, payload.client_id, payload.redirect_uri, payload.state, payload.code_challenge)
    return {"redirect_url": url}


@router.post("/oauth/token", response_model=TokenResponse)
async def token_exchange(
    oauth: OAuthServiceDep,
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    code_verifier: str | None = Form(None),
):
    """RFC 6749 4.1.3: form-encoded, not JSON."""
    if grant_type != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    try:
        token, expires_in = await oauth.exchange_code(client_id, code, redirect_uri, code_verifier)
    except OAuthError as e:
        return JSONResponse({"error": "invalid_grant", "error_description": str(e)}, status_code=400)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/oauth/validate", response_model=TokenValidation)
async def validate_token(oauth: OAuthServiceDep, authorization: str | None = Header(None)):
    """Called by the MCP server for every new connection."""
    raw = (authorization or "").removeprefix("Bearer ").removeprefix("bearer ").strip()
    user = await oauth.user_for_token(raw) if raw else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return TokenValidation(user_id=user["id"], username=user["username"], email=user["email"])


@router.get("/oauth/connections", response_model=list[ConnectedApp])
async def list_connections(current_user: CurrentUser, oauth: OAuthServiceDep):
    return await oauth.list_connections(current_user.id)


@router.delete("/oauth/connections/{token_id}")
async def revoke_connection(token_id: str, current_user: CurrentUser, oauth: OAuthServiceDep):
    if not await oauth.revoke(current_user.id, token_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return {"revoked": True, "id": token_id}
