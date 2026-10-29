from fastapi import APIRouter, HTTPException
from app.api.deps import CurrentUser, DatabaseDep
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent.agent_service import AgentChatService

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: CurrentUser,
    db: DatabaseDep,
):
    try:
        service = AgentChatService(db)
        user_id = str(current_user.id)

        if request.confirm is not None:
            result = await service.confirm(user_id, request.thread_id, request.confirm)
        else:
            if not request.question:
                raise HTTPException(status_code=400, detail="question is required")
            result = await service.ask(user_id, request.thread_id, request.question)

        return ChatResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
