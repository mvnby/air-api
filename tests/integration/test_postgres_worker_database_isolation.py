import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from conftest import TEST_DATABASE_TARGET, TEST_DATABASE_URL
from core.config import settings
from core.database import engine as application_engine


@pytest.mark.parametrize("probe", range(4))
async def test_pytest_worker_uses_its_own_physical_database(db_engine, probe):
    del probe
    async with db_engine.connect() as connection:
        current_database = await connection.scalar(text("SELECT current_database()"))

    assert current_database == TEST_DATABASE_TARGET.database_name
    assert make_url(TEST_DATABASE_URL).database == current_database
    assert make_url(settings.DATABASE_URL).database == current_database
    assert application_engine.url.database == current_database

    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    if os.environ.get("EXPECT_XDIST_DATABASE_ISOLATION") == "1":
        assert worker_id.startswith("gw")
    assert TEST_DATABASE_TARGET.worker_id == worker_id
