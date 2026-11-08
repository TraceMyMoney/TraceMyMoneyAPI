from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, IngestServiceDep, IngestUser
from app.schemas.ingest import ConfirmPendingRequest, IngestSmsRequest

router = APIRouter()


# ── Personal webhook token (managed from the app, so JWT auth) ──────────────
@router.get("/token")
async def token_status(current_user: CurrentUser, ingest: IngestServiceDep):
    """Whether a webhook token exists, and when it was last used."""
    return await ingest.token_status(current_user.id)


@router.post("/token", status_code=201)
async def create_token(current_user: CurrentUser, ingest: IngestServiceDep):
    """Create or rotate the webhook token. The token is shown only in this
    response; any earlier token stops working immediately."""
    return {"token": await ingest.create_token(current_user.id)}


@router.delete("/token")
async def revoke_token(current_user: CurrentUser, ingest: IngestServiceDep):
    if not await ingest.revoke_token(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No webhook token to revoke")
    return {"message": "SUCCESS"}


# ── The webhook itself (token auth: X-Ingest-Token header) ──────────────────
@router.post("/sms")
async def ingest_sms(payload: IngestSmsRequest, user_id: IngestUser, ingest: IngestServiceDep):
    """Receive a forwarded bank / UPI SMS. Parsed transactions land in the
    pending inbox, not in expenses. Messages that aren't transactions (OTPs,
    balance alerts, offers) are ignored, and re-sent messages are deduplicated."""
    result = await ingest.ingest_sms(user_id, payload.text, payload.received_at)
    # 201 only when something new was stored; ignored / duplicate are fine, not errors.
    return JSONResponse(result, status_code=201 if result["status"] == "stored" else 200)


# ── Inbox (JWT auth) ────────────────────────────────────────────────────────
@router.get("/pending")
async def list_pending(
    current_user: CurrentUser,
    ingest: IngestServiceDep,
    status_filter: str = Query("pending", alias="status", pattern="^(pending|confirmed|rejected)$"),
):
    return {"transactions": await ingest.list_pending(current_user.id, status_filter)}


@router.post("/pending/{pending_id}/confirm")
async def confirm_pending(
    pending_id: str, payload: ConfirmPendingRequest, current_user: CurrentUser, ingest: IngestServiceDep
):
    try:
        return await ingest.confirm(
            current_user.id,
            pending_id,
            payload.bank_id,
            payload.description,
            payload.entry_tags,
            payload.amount,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/pending/{pending_id}")
async def reject_pending(pending_id: str, current_user: CurrentUser, ingest: IngestServiceDep):
    if not await ingest.reject(current_user.id, pending_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending transaction not found")
    return {"message": "SUCCESS"}
