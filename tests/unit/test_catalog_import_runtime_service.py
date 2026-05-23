import asyncio

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
async def test_catalog_import_runtime_resumes_running_job_from_database(monkeypatch):
    engine, session_factory = await _sqlite_session_factory()
    monkeypatch.setattr(runtime_module, "async_session_maker", session_factory)

    async with session_factory() as session:
        session.add(
            CatalogImportJob(
                job_id="resume-me",
                status="running",
                stage="importing",
                input_urls=["https://example.com/resume"],
                input_total=1,
            )
        )
        await session.commit()

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
                    }
                )
            return {"success": ["Resumed import product"], "errors": []}

    monkeypatch.setattr(runtime_module, "ImporterService", _FakeImporter)

    service = CatalogImportRuntimeService()
    await service.resume_pending_jobs()

    for _ in range(20):
        current = await service.get_job("resume-me")
        if current and current["status"] == "success":
            break
        await asyncio.sleep(0.05)

    current = await service.get_job("resume-me")
    assert current is not None
    assert current["status"] == "success"
    assert current["successes"] == ["Resumed import product"]

    await engine.dispose()
