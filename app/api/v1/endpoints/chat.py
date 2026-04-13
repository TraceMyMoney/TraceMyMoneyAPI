from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user, get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat.chat_service import ChatService

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        service = ChatService(db=db)
        answer = await service.ask(
            question=request.question,
            user_id=str(current_user.id),
        )
        return ChatResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
