"""
PostgreSQL session management (SQLAlchemy async), introduced alongside the
existing Mongo session (app/db/session.py) per PLAN.md Phase 1.

Both backends coexist during the migration: services are cut over to this
one by one in Phase 3. `app/db/session.py` and Motor are only removed at
cutover (Phase 6), once every service has been rewritten.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Separate engine connected as the restricted smm_chat_readonly role (Phase 4
# Text-to-SQL guardrails). Deliberately never exposed as a FastAPI
# dependency used by the regular CRUD services - only ChatService touches it.
chat_engine: AsyncEngine = create_async_engine(settings.CHAT_DATABASE_URL, pool_pre_ping=True)


async def get_postgres_session() -> AsyncSession:
    """FastAPI dependency yielding a transactional AsyncSession."""
    async with AsyncSessionLocal() as session:
        yield session
