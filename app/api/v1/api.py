from fastapi import APIRouter
from app.api.v1.endpoints import auth, banks, expenses, entry_tags, user_preferences, chat

api_router = APIRouter()

# Register all endpoint routers
api_router.include_router(auth.router, tags=["authentication"])
api_router.include_router(banks.router, prefix="/banks", tags=["banks"])
api_router.include_router(expenses.router, prefix="/expenses", tags=["expenses"])
api_router.include_router(entry_tags.router, prefix="/entry-tags", tags=["entry-tags"])
api_router.include_router(user_preferences.router, prefix="/user-preferences", tags=["user-preferences"])
api_router.include_router(chat.router, prefix="/user", tags=["chat"])
