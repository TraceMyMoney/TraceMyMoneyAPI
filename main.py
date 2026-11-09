import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.oauth import router as oauth_router
from app.api.v1.api import api_router
from app.core.config import settings
from app.db.postgres import AsyncSessionLocal, engine
from app.services.email.worker import worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown."""
    # Background email sender (outbox poller). Requests only queue emails; this
    # task sends them, so nobody waits on Mailgun.
    worker_task = asyncio.create_task(worker_loop(AsyncSessionLocal)) if settings.EMAIL_WORKER_ENABLED else None
    yield
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router)
# OAuth lives at the root (/.well-known, /oauth/*): the specs fix those paths.
app.include_router(oauth_router)
