from fastapi import APIRouter, HTTPException, status
from app.api.deps import CurrentUser, EntryTagServiceDep
from app.schemas.entry_tag import EntryTagCreate, EntryTagResponse

router = APIRouter()


@router.get("/")
async def get_entry_tags(current_user: CurrentUser, tag_service: EntryTagServiceDep):
    """Get all entry tags for the current user."""
    tags = await tag_service.get_tags(current_user.id)

    return {"entry_tags": [{"id": tag.id, "name": tag.name, "created_at": tag.created_at} for tag in tags]}


@router.post("/create", status_code=201)
async def create_entry_tag(
    tag_data: EntryTagCreate, current_user: CurrentUser, tag_service: EntryTagServiceDep
):
    """Create a new entry tag."""
    try:
        tag = await tag_service.create_tag(current_user.id, tag_data)
        return {"success": "Tag created successfully", "tag_id": tag.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
