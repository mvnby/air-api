import asyncio
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import CatalogImportJob
from services import catalog_import_runtime_service as runtime_module
from services.catalog_import_runtime_service import CatalogImportRuntimeService


async def _sqlite_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


@pytest.mark.asyncio
async def test_catalog_import_job_is_persisted_and_progress_updates(monkeypatch):
    engine, session_factory = await _sqlite_session_factory()
    monkeypatch.setattr(runtime_module, "async_session_maker", session_factory)

    class _FakeImporter:
        async def import_products_bulk(
            self,
            urls,
            with_related=False,  # noqa: ARG002
            update_existing=False,  # noqa: ARG002
            progress_callback=None,
        ):
            if progress_callback:
                await progress_callback(
                    {
                        "stage": "importing",
                        "total": len(urls),
                        "processed": 1,
                        "pending": 0,
                        "success_count": 1,
                        "error_count": 0,
                        "current_url": urls[0],
                        "current_title": "Persisted import product",
                    }
                )
            return {"success": ["Persisted import product"], "errors": []}

    monkeypatch.setattr(runtime_module, "ImporterService", _FakeImporter)

    service = CatalogImportRuntimeService()
    started = await service.start_import(
        urls=["https://example.com/product"],
        with_related=True,
        update_existing=False,
    )

    for _ in range(20):
        current = await service.get_job(started["job_id"])
        if current and current["status"] == "success":
            break
        await asyncio.sleep(0.05)

    current = await service.get_current_job()
    assert current is not None
    assert current["job_id"] == started["job_id"]
    assert current["status"] == "success"
    assert current["processed"] == 1
    assert current["successes"] == ["Persisted import product"]

    async with session_factory() as session:
        row = (await session.execute(select(CatalogImportJob))).scalar_one()
        assert row.job_id == started["job_id"]
        assert row.input_urls == ["https://example.com/product"]
        assert row.with_related is True
        assert row.status == "success"

    await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_import_runtime_leaves_running_job_untouched(monkeypatch):
    engine, session_factory = await _sqlite_session_factory()
    monkeypatch.setattr(runtime_module, "async_session_maker", session_factory)

    async with session_factory() as session:
        session.add_all(
            [
                CatalogImportJob(
                    job_id="already-running",
                    status="running",
                    stage="importing",
                    error="preserve-me",
                    input_urls=["https://example.com/running"],
                    input_total=1,
                ),
                CatalogImportJob(
                    job_id="queued-behind-running",
                    status="queued",
                    stage="queued",
                    input_urls=["https://example.com/queued"],
                    input_total=1,
                ),
            ]
        )
        await session.commit()

    service = CatalogImportRuntimeService()
    schedule_job = Mock(return_value=True)
    monkeypatch.setattr(service, "_schedule_job", schedule_job)

    assert await service.resume_pending_jobs() is False

    async with session_factory() as session:
        running = await session.get(CatalogImportJob, "already-running")
        queued = await session.get(CatalogImportJob, "queued-behind-running")
        assert running is not None
        assert running.status == "running"
        assert running.stage == "importing"
        assert running.error == "preserve-me"
        assert queued is not None
        assert queued.status == "queued"
    schedule_job.assert_not_called()

    await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_import_runtime_starts_queued_job_when_none_running(monkeypatch):
    engine, session_factory = await _sqlite_session_factory()
    monkeypatch.setattr(runtime_module, "async_session_maker", session_factory)

    async with session_factory() as session:
        session.add(
            CatalogImportJob(
                job_id="ready-to-start",
                status="queued",
                stage="queued",
                input_urls=["https://example.com/queued"],
                input_total=1,
            )
        )
        await session.commit()

    service = CatalogImportRuntimeService()
    schedule_job = Mock(return_value=True)
    monkeypatch.setattr(service, "_schedule_job", schedule_job)

    assert await service.resume_pending_jobs() is True
    schedule_job.assert_called_once_with("ready-to-start")

    await engine.dispose()
