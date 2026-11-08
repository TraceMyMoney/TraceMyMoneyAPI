from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    banks,
    chat,
    entry_tags,
    expenses,
    ingest,
    profile,
    settings,
    user_preferences,
)

api_router = APIRouter()

# Register all endpoint routers
api_router.include_router(auth.router, tags=["authentication"])
api_router.include_router(banks.router, prefix="/banks", tags=["banks"])
api_router.include_router(expenses.router, prefix="/expenses", tags=["expenses"])
api_router.include_router(entry_tags.router, prefix="/entry-tags", tags=["entry-tags"])
api_router.include_router(user_preferences.router, prefix="/user-preferences", tags=["user-preferences"])
api_router.include_router(chat.router, prefix="/user", tags=["chat"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
