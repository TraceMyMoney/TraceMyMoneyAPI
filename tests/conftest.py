"""
Shared fixtures for characterization tests.

These tests pin down the API's behavior against the PostgreSQL backend
(see PLAN.md). They originally ran against mongomock-motor during Phase 0;
now that Phase 3 has cut every service over to Postgres, they run against a
real `stalk_my_money_test` database (same cluster as docker-compose.dev.yml,
schema applied via `alembic upgrade head` - see PLAN.md Phase 2/3 notes).
Tables are truncated after every test for isolation.
"""

import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.db.tables import metadata
from main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://smm:smm@localhost:5432/stalk_my_money_test"
)

test_engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def test_db():
    """A SQLAlchemy AsyncSession against the test database, truncated after each test."""
    async with TestSessionLocal() as session:
        yield session

    table_names = ", ".join(f'"{t.name}"' for t in metadata.sorted_tables)
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {table_names} CASCADE"))


@pytest_asyncio.fixture
async def client(test_db):
    """An HTTP client wired to the FastAPI app with the test session injected."""

    async def _get_test_db():
        return test_db

    app.dependency_overrides[get_db] = _get_test_db

    # raise_app_exceptions=False: unhandled exceptions become HTTP 500 responses,
    # matching production (uvicorn) behavior instead of propagating as Python
    # exceptions in the test process.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def registered_user(client):
    """Registers a user and returns their credentials."""
    payload = {
        "username": "characterization",
        "email": "characterization@example.com",
        "password": "testpass123",
    }
    resp = await client.post("/register", json=payload)
    assert resp.status_code == 200, resp.text
    return {"username": payload["username"], "password": payload["password"], "user_id": resp.json()["user_id"]}


@pytest_asyncio.fixture
async def auth_headers(client, registered_user):
    """Logs in the registered user and returns Authorization headers."""
    resp = await client.post(
        "/login", json={"username": registered_user["username"], "password": registered_user["password"]}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def created_bank(client, auth_headers):
    """Creates a bank and returns its API response payload."""
    resp = await client.post(
        "/banks/create",
        json={"name": "Chase", "initial_balance": 5000.0, "current_balance": 5000.0},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    banks_resp = await client.get("/banks/", headers=auth_headers)
    return banks_resp.json()["banks"][0]
