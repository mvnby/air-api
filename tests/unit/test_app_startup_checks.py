from types import SimpleNamespace

import pytest

from core import app_lifespan as lifespan_module


@pytest.mark.asyncio
async def test_app_lifespan_awaits_startup_checks_before_database(monkeypatch):
    events: list[str] = []

    async def run_startup_checks(_settings):
        events.append("startup_checks")

    async def bootstrap_database():
        events.append("database")

    def start_scheduler(_app):
        events.append("scheduler")

    async def stop_scheduler(_app):
        events.append("shutdown")

    monkeypatch.setattr(
        lifespan_module,
        "run_production_startup_checks",
        run_startup_checks,
    )
    monkeypatch.setattr(lifespan_module, "_bootstrap_database", bootstrap_database)
    monkeypatch.setattr(
        lifespan_module,
        "_start_scheduler_supervisor",
        start_scheduler,
    )
    monkeypatch.setattr(
        lifespan_module,
        "_stop_scheduler_supervisor",
        stop_scheduler,
    )

    async with lifespan_module.app_lifespan(SimpleNamespace()):
        events.append("serving")

    assert events == [
        "startup_checks",
        "database",
        "scheduler",
        "serving",
        "shutdown",
    ]


@pytest.mark.asyncio
async def test_app_lifespan_fails_before_database_when_startup_check_fails(
    monkeypatch,
):
    async def fail_startup_checks(_settings):
        raise RuntimeError("private storage unavailable")

    async def bootstrap_database():
        raise AssertionError("database bootstrap must not start")

    monkeypatch.setattr(
        lifespan_module,
        "run_production_startup_checks",
        fail_startup_checks,
    )
    monkeypatch.setattr(lifespan_module, "_bootstrap_database", bootstrap_database)

    with pytest.raises(RuntimeError, match="private storage unavailable"):
        async with lifespan_module.app_lifespan(SimpleNamespace()):
            raise AssertionError("application must not start serving")
