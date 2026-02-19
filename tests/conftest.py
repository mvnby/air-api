import os
import asyncio
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# CRITICAL: Always use the TEST database for tests.
# Construct the test DB URL from env vars, pointing to the db_test service.
_pg_user = os.environ.get("POSTGRES_USER", "mvnadmin")
_pg_pass = os.environ.get("POSTGRES_PASSWORD", "securepass")
_test_db_host = os.environ.get("TEST_DB_HOST", "db_test")  # Docker service name
_test_db_port = os.environ.get("TEST_DB_PORT", "5432")
_test_db_name = "air_conditioners_test"
TEST_DATABASE_URL = f"postgresql+asyncpg://{_pg_user}:{_pg_pass}@{_test_db_host}:{_test_db_port}/{_test_db_name}"

# Safety net: abort if the URL doesn't contain 'test'
assert "test" in TEST_DATABASE_URL.lower(), (
    f"SAFETY: Refusing to run tests against a non-test database! URL={TEST_DATABASE_URL}"
)

# event_loop fixture removed to let pytest-asyncio handle it with scope=session


@pytest.fixture(scope="function")
async def db_engine():
    """
    Create a fresh database engine for the test session.
    Always uses the dedicated test database (db_test service).
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Basic check if DB is up
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
    await engine.dispose()

@pytest.fixture(scope="function")
async def db(db_engine):
    """
    Yields a fresh session for each test.
    The session is rolled back after the test.
    """
    # Connect to the database
    connection = await db_engine.connect()
    # Begin a non-ORM transaction
    transaction = await connection.begin()
    
    # Bind an individual Session to the connection
    session_factory = sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with session_factory() as session:
        yield session
    
    # Rollback the setup transaction
    await transaction.rollback()
    await connection.close()

@pytest.fixture(scope="function")
async def async_client(db):
    from httpx import AsyncClient, ASGITransport
    from main import app
    from core.database import get_session

    async def override_get_session():
        yield db

    app.dependency_overrides[get_session] = override_get_session
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()
