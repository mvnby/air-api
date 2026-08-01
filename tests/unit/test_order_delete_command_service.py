from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, IntegrationOutboxEvent, Order, OrderDocument, OrderStatus
from models.tenancy import TenantScope
from services.order_delete_command_service import OrderDeleteCommandService
from services.order_document_cleanup_service import OrderDocumentCleanupService


TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def delete_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'order_delete_command.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_rolls_back_order_and_cleanup_event_together(
    delete_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    customer = Customer(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        name="Delete rollback customer",
        phone="+375290000005",
    )
    delete_session.add(customer)
    await delete_session.flush()
    order = Order(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        storefront_id=TEST_TENANT_SCOPE.storefront_id,
        customer_id=customer.id,
        status=OrderStatus.NEW_LEAD,
    )
    delete_session.add(order)
    await delete_session.flush()
    document = OrderDocument(
        order_id=order.id,
        doc_type="contract",
        number="ROLLBACK-1",
        google_file_id="drive-file-rollback",
        google_edit_url="https://docs.google.com/document/d/drive-file-rollback/edit",
    )
    delete_session.add(document)
    await delete_session.commit()
    order_id = int(order.id)
    document_id = int(document.id)

    original_enqueue = OrderDocumentCleanupService.enqueue_order_documents

    async def enqueue_then_fail(*args, **kwargs):
        await original_enqueue(*args, **kwargs)
        raise RuntimeError("injected final-step failure")

    monkeypatch.setattr(
        OrderDocumentCleanupService,
        "enqueue_order_documents",
        enqueue_then_fail,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderDeleteCommandService.delete_order(
            delete_session,
            order_id,
            tenant_scope=TEST_TENANT_SCOPE,
        )

    assert await delete_session.get(Order, order_id) is not None
    assert await delete_session.get(OrderDocument, document_id) is not None
    events = list(
        (await delete_session.execute(select(IntegrationOutboxEvent))).scalars()
    )
    assert events == []
