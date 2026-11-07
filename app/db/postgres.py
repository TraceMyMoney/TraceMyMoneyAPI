"""
PostgreSQL session management (SQLAlchemy async). See PLAN.md.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_postgres_session() -> AsyncSession:
    """FastAPI dependency yielding a transactional AsyncSession."""
    async with AsyncSessionLocal() as session:
        yield session
