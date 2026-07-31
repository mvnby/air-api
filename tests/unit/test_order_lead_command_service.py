from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, Lead, LeadStatus, Order, OrderProposal
from models.tenancy import TenantScope
from schemas import (
    LeadCreatePayload,
    LeadLossPayload,
    LeadQualifyPayload,
    LeadUpdatePayload,
    ManagerOrderCreatePayload,
)
from services.lead_command_service import LeadCommandService
from services.order_create_command_service import OrderCreateCommandService
from services.order_service import OrderService


TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def command_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'order_lead_commands.db'}",
        echo=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _create_lead(session: AsyncSession) -> int:
    lead = Lead(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        storefront_id=TEST_TENANT_SCOPE.storefront_id,
        name="Исходный лид",
        request_text="Исходная заявка",
    )
    session.add(lead)
    await session.commit()
    return int(lead.id)


def _raise_after_flush(original_flush, *, fail_on_call: int = 1):
    call_count = 0

    async def flush_then_fail(session: AsyncSession, *args, **kwargs) -> None:
        nonlocal call_count
        await original_flush(session, *args, **kwargs)
        call_count += 1
        if call_count == fail_on_call:
            raise RuntimeError("injected final-step failure")

    return flush_then_fail


@pytest.mark.asyncio
async def test_create_manager_order_rolls_back_customer_order_and_proposal(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fail_after_create(
        _session: AsyncSession,
        _order: Order,
    ) -> None:
        raise RuntimeError("injected final-step failure")

    monkeypatch.setattr(
        OrderService,
        "_maybe_add_default_repair_diagnostic",
        fail_after_create,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderCreateCommandService.create_manager_order(
            command_session,
            ManagerOrderCreatePayload(
                source="manager",
                request_text="Диагностика кондиционера",
                service_type="repair",
                name="Новый клиент",
                phone="+375290000003",
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    assert list((await command_session.execute(select(Customer))).scalars()) == []
    assert list((await command_session.execute(select(Order))).scalars()) == []
    assert list((await command_session.execute(select(OrderProposal))).scalars()) == []


@pytest.mark.asyncio
async def test_create_lead_rolls_back_flushed_row(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        AsyncSession,
        "flush",
        _raise_after_flush(AsyncSession.flush),
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await LeadCommandService.create_lead(
            command_session,
            LeadCreatePayload(
                source="manager",
                name="Новый лид",
                request_text="Нужен кондиционер",
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    assert list((await command_session.execute(select(Lead))).scalars()) == []


@pytest.mark.asyncio
async def test_update_lead_rolls_back_flushed_fields(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    lead_id = await _create_lead(command_session)
    monkeypatch.setattr(
        AsyncSession,
        "flush",
        _raise_after_flush(AsyncSession.flush),
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await LeadCommandService.update_lead(
            command_session,
            lead_id,
            LeadUpdatePayload(name="Не должно сохраниться"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    command_session.expire_all()
    stored = await command_session.get(Lead, lead_id)
    assert stored is not None
    assert stored.name == "Исходный лид"


@pytest.mark.asyncio
async def test_mark_lead_lost_rolls_back_flushed_status(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    lead_id = await _create_lead(command_session)
    monkeypatch.setattr(
        AsyncSession,
        "flush",
        _raise_after_flush(AsyncSession.flush),
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await LeadCommandService.mark_lead_lost(
            command_session,
            lead_id,
            LeadLossPayload(status="lost", loss_reason="no_product"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    command_session.expire_all()
    stored = await command_session.get(Lead, lead_id)
    assert stored is not None
    assert stored.status == LeadStatus.new
    assert stored.loss_reason is None


@pytest.mark.asyncio
async def test_qualify_lead_rolls_back_customer_order_and_conversion(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    lead_id = await _create_lead(command_session)
    monkeypatch.setattr(
        AsyncSession,
        "flush",
        _raise_after_flush(AsyncSession.flush, fail_on_call=3),
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await LeadCommandService.qualify_lead(
            command_session,
            lead_id,
            LeadQualifyPayload(order_comment="Квалифицировать атомарно"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    command_session.expire_all()
    stored = await command_session.get(Lead, lead_id)
    assert stored is not None
    assert stored.status == LeadStatus.new
    assert stored.converted_order_id is None
    assert list((await command_session.execute(select(Customer))).scalars()) == []
    assert list((await command_session.execute(select(Order))).scalars()) == []
