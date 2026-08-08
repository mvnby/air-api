import asyncio
import copy
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import Order
from services.defect_act_ai_service import DefectActAIService
from services.order_service import OrderService
from services.repair_diagnostic_ai_job_service import (
    RepairDiagnosticAiJobService,
)
from tests.unit.test_repair_diagnostic_ai_job_service import _load, _seed_job


@pytest.fixture
async def repair_ai_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'repair-ai-concurrency.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_runs_without_open_order_transaction_and_three_way_merges(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()

    async def delayed_provider(_payload):
        provider_started.set()
        await release_provider.wait()
        return {
            "diagnostic_result": "AI result",
            "recommended_actions": ["inspect"],
        }

    monkeypatch.setattr(
        DefectActAIService,
        "generate_repair_meta",
        delayed_provider,
    )
    worker = asyncio.create_task(
        RepairDiagnosticAiJobService.process_batch(
            worker_id="concurrent-manager-worker",
            limit=1,
            session_factory=repair_ai_factory,
        )
    )
    await asyncio.wait_for(provider_started.wait(), timeout=2)

    async with repair_ai_factory() as manager_session:
        order = await manager_session.get(Order, order_id)
        technical_meta = copy.deepcopy(order.technical_meta)
        repair_meta = copy.deepcopy(technical_meta["repair"])
        repair_meta["diagnostic_result"] = "Manager result"
        repair_meta["manager_note"] = "keep this edit"
        technical_meta["repair"] = repair_meta
        technical_meta["manager_top_level"] = {"keep": True}
        order.technical_meta = technical_meta
        manager_session.add(order)
        await manager_session.commit()

    release_provider.set()
    assert await asyncio.wait_for(worker, timeout=3) == 1
    order, event = await _load(repair_ai_factory, order_id, event_id)
    repair_meta = OrderService._get_repair_meta(order)
    assert event.status == "published"
    assert repair_meta["ai_pre_diagnosis_status"] == "completed"
    assert repair_meta["diagnostic_result"] == "Manager result"
    assert repair_meta["manager_note"] == "keep this edit"
    assert repair_meta["recommended_actions"] == ["inspect"]
    assert order.technical_meta["manager_top_level"] == {"keep": True}


@pytest.mark.asyncio
async def test_latest_terminal_manager_state_is_not_overwritten_by_stale_ai(
    repair_ai_factory,
    monkeypatch,
):
    order_id, event_id = await _seed_job(repair_ai_factory)
    monkeypatch.setattr(
        "services.repair_diagnostic_ai_service.async_session_maker",
        repair_ai_factory,
    )
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()

    async def delayed_provider(_payload):
        provider_started.set()
        await release_provider.wait()
        return {"diagnostic_result": "stale AI result"}

    monkeypatch.setattr(
        DefectActAIService,
        "generate_repair_meta",
        delayed_provider,
    )
    worker = asyncio.create_task(
        RepairDiagnosticAiJobService.process_batch(
            worker_id="terminal-manager-worker",
            limit=1,
            session_factory=repair_ai_factory,
        )
    )
    await asyncio.wait_for(provider_started.wait(), timeout=2)

    async with repair_ai_factory() as manager_session:
        order = await manager_session.get(Order, order_id)
        repair_meta = OrderService._get_repair_meta(order)
        repair_meta["ai_pre_diagnosis_status"] = "completed"
        repair_meta["diagnostic_result"] = "manager terminal result"
        OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )
        manager_session.add(order)
        await manager_session.commit()

    release_provider.set()
    assert await asyncio.wait_for(worker, timeout=3) == 1
    order, event = await _load(repair_ai_factory, order_id, event_id)
    repair_meta = OrderService._get_repair_meta(order)
    assert event.status == "published"
    assert repair_meta["ai_pre_diagnosis_status"] == "completed"
    assert repair_meta["diagnostic_result"] == "manager terminal result"
