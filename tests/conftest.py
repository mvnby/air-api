import os
import asyncio
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Tests should never emit events into the real Sentry project, even when a
# developer has production-like values in a local .env.
os.environ["ENVIRONMENT"] = "test"
os.environ["SENTRY_DSN"] = ""


def _running_inside_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolve_test_database_url() -> str:
    configured_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if configured_url and "test" in configured_url.lower():
        return configured_url

    pg_user = os.environ.get("POSTGRES_USER", "mvnadmin")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "securepass")
    test_db_host = os.environ.get("TEST_DB_HOST")
    if not test_db_host:
        test_db_host = "db_test" if _running_inside_docker() else "localhost"
    test_db_port = os.environ.get("TEST_DB_PORT") or os.environ.get("POSTGRES_PORT")
    if not test_db_port:
        test_db_port = "5432" if test_db_host == "db_test" else "5433"
    test_db_name = os.environ.get("TEST_POSTGRES_DB", "air_conditioners_test")
    return f"postgresql+asyncpg://{pg_user}:{pg_pass}@{test_db_host}:{test_db_port}/{test_db_name}"


# CRITICAL: Always use the TEST database for tests.
TEST_DATABASE_URL = _resolve_test_database_url()

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
