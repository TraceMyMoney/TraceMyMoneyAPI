from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, EntryTagServiceDep
from app.schemas.entry_tag import EntryTagCreate, EntryTagUpdate
from app.services.jev_insights import suggest_tag

router = APIRouter()


class SuggestTagRequest(BaseModel):
    description: str


class SuggestTagResponse(BaseModel):
    tag_name: str | None = None
    confidence: float | None = None


def _tag_json(tag) -> dict:
    return {"id": tag.id, "name": tag.name, "created_at": tag.created_at, "entry_count": tag.entry_count}


@router.get("/")
async def get_entry_tags(current_user: CurrentUser, tag_service: EntryTagServiceDep):
    """Get all entry tags for the current user."""
    tags = await tag_service.get_tags(current_user.id)

    return {"entry_tags": [_tag_json(tag) for tag in tags]}


@router.post("/create", status_code=201)
async def create_entry_tag(tag_data: EntryTagCreate, current_user: CurrentUser, tag_service: EntryTagServiceDep):
    """Create a new entry tag."""
    try:
        tag = await tag_service.create_tag(current_user.id, tag_data)
        return {"success": "Tag created successfully", "tag_id": tag.id, "name": tag.name}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{tag_id}")
async def rename_entry_tag(
    tag_id: str, tag_data: EntryTagUpdate, current_user: CurrentUser, tag_service: EntryTagServiceDep
):
    """Rename a tag. 404 if it is not one of the user's tags, 400 if the name is taken."""
    try:
        tag = await tag_service.update_tag(current_user.id, tag_id, tag_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return {"success": "Tag renamed successfully", "tag": _tag_json(tag)}


@router.delete("/{tag_id}")
async def delete_entry_tag(tag_id: str, current_user: CurrentUser, tag_service: EntryTagServiceDep):
    """Delete a tag. Entries keep their amounts and other tags; they only lose this one."""
    entries_untagged = await tag_service.delete_tag(current_user.id, tag_id)
    if entries_untagged is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return {"success": "Tag deleted successfully", "entries_untagged": entries_untagged}


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
