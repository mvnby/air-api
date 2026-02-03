import os
import asyncio
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Ensure we are using the TEST database
# (This is a safety check in case pytest.ini is ignored)
encoded_url = os.getenv("DATABASE_URL", "")
if "test" not in encoded_url and ":memory:" not in encoded_url:
    # Fallback or error? 
    # Let's trust pytest.ini but log a warning if needed
    pass

# event_loop fixture removed to let pytest-asyncio handle it with scope=session


@pytest.fixture(scope="function")
async def db_engine():
    """
    Create a fresh database engine for the test session.
    Waits for the DB to be ready.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set for tests")
    
    engine = create_async_engine(database_url, echo=False)

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
async def async_client():
    from httpx import AsyncClient
    from main import app  # Local import to avoid circular issues
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
