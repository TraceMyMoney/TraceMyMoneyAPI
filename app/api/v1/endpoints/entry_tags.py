from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, EntryTagServiceDep
from app.schemas.entry_tag import EntryTagCreate
from app.services.jev_insights import suggest_tag

router = APIRouter()


class SuggestTagRequest(BaseModel):
    description: str


class SuggestTagResponse(BaseModel):
    tag_name: str | None = None
    confidence: float | None = None


@router.get("/")
async def get_entry_tags(current_user: CurrentUser, tag_service: EntryTagServiceDep):
    """Get all entry tags for the current user."""
    tags = await tag_service.get_tags(current_user.id)

    return {"entry_tags": [{"id": tag.id, "name": tag.name, "created_at": tag.created_at} for tag in tags]}


@router.post("/create", status_code=201)
async def create_entry_tag(tag_data: EntryTagCreate, current_user: CurrentUser, tag_service: EntryTagServiceDep):
    """Create a new entry tag."""
    try:
        tag = await tag_service.create_tag(current_user.id, tag_data)
        return {"success": "Tag created successfully", "tag_id": tag.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/suggest", response_model=SuggestTagResponse)
async def suggest_entry_tag(payload: SuggestTagRequest, current_user: CurrentUser, tag_service: EntryTagServiceDep):
    """Suggest an existing tag for a new expense description, via Jev
    (TypeSafe AI). Returns an empty body (both fields null) whenever Jev
    isn't configured/available or no match was found - this is advisory
    only, never required for adding an expense."""
    tags = await tag_service.get_tags(current_user.id)
    result = await suggest_tag(payload.description, [t.name for t in tags])
    if result is None:
        return SuggestTagResponse()
    return SuggestTagResponse(**result)
