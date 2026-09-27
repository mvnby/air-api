from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, CustomerBranch, CustomerType, Lead, LeadStatus, Order, OrderProposal, OrderStatus
from models.tenancy import TenantScope
from schemas import (
    LeadCreatePayload,
    LeadLossPayload,
    LeadQualifyPayload,
    LeadUpdatePayload,
    ManagerOrderCreatePayload,
    ManagerOrderUpdatePayload,
)
from services.lead_command_service import LeadCommandService
from services.lead_service import LeadService
from services.order_create_command_service import OrderCreateCommandService
from services.order_service import OrderService
from services.order_update.command import OrderUpdateCommandService


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
        *,
        tenant_scope: TenantScope,
    ) -> None:
        assert tenant_scope == TEST_TENANT_SCOPE
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


@pytest.mark.parametrize("match_by", ["id", "phone"])
@pytest.mark.parametrize(
    ("party_type", "signing_mode"),
    [(CustomerType.company, "statutory_body"), (CustomerType.company, "power_of_attorney"),
     (CustomerType.individual_entrepreneur, "self"), (CustomerType.individual, "self")],
)
async def test_manager_order_preserves_customer_party_when_type_is_omitted(
    command_session, match_by, party_type, signing_mode,
):
    customer = Customer(
        tenant_id=1, name='Частное торговое унитарное предприятие "МЭДО"',
        phone="+375291234567", type=party_type, signing_mode=signing_mode,
    )
    command_session.add(customer)
    await command_session.commit()
    match = {"customer_id": customer.id} if match_by == "id" else {"phone": customer.phone}
    result = await OrderCreateCommandService.create_manager_order(
        command_session,
        ManagerOrderCreatePayload(source="manager", request_text="Новый заказ", **match),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    await command_session.refresh(customer)
    order = await command_session.get(Order, result["id"])
    assert order.customer_id == customer.id
    assert customer.type == party_type
    assert customer.signing_mode == signing_mode


@pytest.mark.parametrize("selected_type", [None, "company", "individual_entrepreneur"])
async def test_manager_order_creates_customer_with_default_or_selected_type(command_session, selected_type):
    fields = {"customer_type": selected_type} if selected_type else {}
    result = await OrderCreateCommandService.create_manager_order(
        command_session,
        ManagerOrderCreatePayload(
            source="manager", request_text="Новый заказ", name="Новый клиент", **fields,
        ),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    order = await command_session.get(Order, result["id"])
    customer = await command_session.get(Customer, order.customer_id)
    assert customer.type == (selected_type or "individual")
    assert customer.signing_mode == ("statutory_body" if selected_type == "company" else "self")


@pytest.mark.asyncio
async def test_manager_order_uses_explicit_scenario_without_comment_or_scheduling(command_session):
    customer = Customer(tenant_id=1, name="Клиент", phone="", type=CustomerType.company)
    command_session.add(customer)
    await command_session.commit()
    result = await OrderCreateCommandService.create_manager_order(
        command_session,
        ManagerOrderCreatePayload(
            source="manager",
            customer_id=customer.id,
            workflow_type="maintenance",
            service_type="maintenance",
            target_date="2026-10-02T09:00:00",
            contact_name="Сергей",
        ),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    order = await command_session.get(Order, result["id"])
    assert order.status == OrderStatus.NEGOTIATION
    assert order.workflow_type == "maintenance"
    assert order.title == "Обслуживание"
    assert order.comment is None
    assert order.installation_date is None
    assert order.technical_meta["requested_date"] == "2026-10-02"
    assert order.technical_meta["contact_name"] == "Сергей"
    assert str(result["requested_date"]) == "2026-10-02"
    assert result["contact_name"] == "Сергей"
    assert result["contact_phone"] is None

    edited = await OrderUpdateCommandService.update_order_for_manager(
        command_session, result["id"],
        ManagerOrderUpdatePayload(
            title="Плановое обслуживание",
            requested_date="2026-10-04",
            contact_name="Новый контакт",
            contact_phone="+375291234567",
        ),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert edited["title"] == "Плановое обслуживание"
    assert str(edited["requested_date"]) == "2026-10-04"
    assert (edited["contact_name"], edited["contact_phone"]) == (
        "Новый контакт", "+375291234567",
    )
    assert edited["installation_date"] is None
    cleared = await OrderUpdateCommandService.update_order_for_manager(
        command_session, result["id"],
        ManagerOrderUpdatePayload(requested_date=None, contact_name=None, contact_phone=None),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert cleared["requested_date"] is None
    assert cleared["contact_name"] is None
    assert cleared["contact_phone"] is None


@pytest.mark.asyncio
async def test_manager_generic_works_clears_service_and_preserves_customer_address(command_session):
    customer = Customer(tenant_id=1, name="Клиент", phone="", actual_address="Юрадрес")
    command_session.add(customer)
    await command_session.commit()
    branch = CustomerBranch(customer_id=customer.id, delivery_address="Объект филиала")
    command_session.add(branch)
    await command_session.commit()
    result = await OrderCreateCommandService.create_manager_order(
        command_session,
        ManagerOrderCreatePayload(
            source="manager", customer_id=customer.id,
            workflow_type="service_work", service_type=None,
            customer_branch_id=branch.id,
        ),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    order = await command_session.get(Order, result["id"])
    await command_session.refresh(customer)
    assert (order.workflow_type, order.title) == ("service_work", "Работы")
    assert order.customer_branch_id == branch.id
    assert order.delivery_address == "Объект филиала"
    assert "service_type" not in order.technical_meta
    assert customer.actual_address == "Юрадрес"


@pytest.mark.asyncio
async def test_manager_create_rejects_conflicting_scenario_and_foreign_branch(command_session):
    customer = Customer(tenant_id=1, name="Первый", phone="")
    other = Customer(tenant_id=1, name="Другой", phone="")
    command_session.add_all([customer, other])
    await command_session.commit()
    branch = CustomerBranch(customer_id=other.id, delivery_address="Чужой адрес")
    command_session.add(branch)
    await command_session.commit()
    customer_id, branch_id = customer.id, branch.id
    with pytest.raises(ValueError, match="conflicts"):
        await OrderCreateCommandService.create_manager_order(
            command_session,
            ManagerOrderCreatePayload(
                source="manager", customer_id=customer_id,
                workflow_type="repair", service_type="install_only",
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )
    with pytest.raises(ValueError, match="branch"):
        await OrderCreateCommandService.create_manager_order(
            command_session,
            ManagerOrderCreatePayload(
                source="manager", customer_id=customer_id,
                workflow_type="service_work", customer_branch_id=branch_id,
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )
    assert list((await command_session.execute(select(Order))).scalars()) == []


@pytest.mark.asyncio
async def test_manager_create_idempotency_uses_intent_not_order_contents(command_session):
    customer = Customer(tenant_id=1, name="Клиент", phone="")
    command_session.add(customer)
    await command_session.commit()
    customer_id = customer.id
    request_id = uuid4()
    payload = ManagerOrderCreatePayload(
        source="manager", customer_id=customer_id,
        client_request_id=request_id,
        workflow_type="service_work", service_type="install_only",
    )
    first = await OrderCreateCommandService.create_manager_order(
        command_session, payload, tenant_scope=TEST_TENANT_SCOPE,
    )
    repeated = await OrderCreateCommandService.create_manager_order(
        command_session, payload, tenant_scope=TEST_TENANT_SCOPE,
    )
    distinct = await OrderCreateCommandService.create_manager_order(
        command_session,
        payload.model_copy(update={"client_request_id": uuid4()}),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert first["id"] == repeated["id"]
    assert distinct["id"] != first["id"]
    assert len(list((await command_session.execute(select(Order))).scalars())) == 2


@pytest.mark.asyncio
async def test_lead_qualification_preserves_selected_customer_and_conversion(command_session):
    lead_id = await _create_lead(command_session)
    customer = Customer(tenant_id=1, name="Известный клиент", phone="", type=CustomerType.company)
    command_session.add(customer)
    await command_session.commit()
    customer_id = customer.id
    payload = LeadQualifyPayload(
        customer_id=customer_id,
        name="Имя из лида",
        phone="+375291234567",
        workflow_type="maintenance",
        service_type="maintenance",
    )
    first = await LeadCommandService.qualify_lead(
        command_session, lead_id, payload, tenant_scope=TEST_TENANT_SCOPE,
    )
    repeated = await LeadCommandService.qualify_lead(
        command_session, lead_id, payload, tenant_scope=TEST_TENANT_SCOPE,
    )
    await command_session.refresh(customer)
    order = await command_session.get(Order, first["order_id"])
    assert (customer.name, customer.phone) == ("Известный клиент", "")
    assert order.comment == "Исходная заявка"
    assert (order.status, order.workflow_type) == (OrderStatus.NEGOTIATION, "maintenance")
    assert order.technical_meta["service_type"] == "maintenance"
    assert repeated["order_id"] == first["order_id"]
    assert repeated["order_created"] is False


def test_customer_match_rejects_multiple_normalized_phone_matches():
    first = Customer(id=1, tenant_id=1, name="Первый", phone="+375 (29) 123-45-67")
    second = Customer(id=2, tenant_id=1, name="Второй", phone="375291234567")
    with pytest.raises(ValueError, match="select customer_id explicitly"):
        LeadService._select_unique_customer_match(
            [first, second], phone="+375 29 123 45 67", email=None, inn=None,
        )


@pytest.mark.asyncio
async def test_lead_qualification_rejects_conflicting_inn_and_email_matches(command_session):
    lead_id = await _create_lead(command_session)
    by_inn = Customer(tenant_id=1, name="По УНП", phone="", inn="123456789")
    by_email = Customer(tenant_id=1, name="По почте", phone="", email="same@example.com")
    command_session.add_all([by_inn, by_email])
    await command_session.commit()
    with pytest.raises(ValueError, match="select customer_id explicitly"):
        await LeadCommandService.qualify_lead(
            command_session, lead_id,
            LeadQualifyPayload(inn="123456789", email="same@example.com"),
            tenant_scope=TEST_TENANT_SCOPE,
        )
    stored_lead = await command_session.get(Lead, lead_id)
    assert stored_lead.status == LeadStatus.new
    assert stored_lead.converted_order_id is None
    assert list((await command_session.execute(select(Order))).scalars()) == []


@pytest.mark.asyncio
async def test_lead_qualification_prefers_unique_exact_inn(command_session):
    lead_id = await _create_lead(command_session)
    customer = Customer(tenant_id=1, name="По УНП", phone="", inn="123456789")
    command_session.add(customer)
    await command_session.commit()
    customer_id = customer.id
    result = await LeadCommandService.qualify_lead(
        command_session, lead_id,
        LeadQualifyPayload(inn="123456789"),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert result["customer_id"] == customer_id


@pytest.mark.asyncio
async def test_switch_to_generic_works_removes_stale_service_kind(command_session):
    customer = Customer(tenant_id=1, name="Клиент", phone="")
    command_session.add(customer)
    await command_session.commit()
    created = await OrderCreateCommandService.create_manager_order(
        command_session,
        ManagerOrderCreatePayload(
            source="manager", customer_id=customer.id,
            workflow_type="maintenance", service_type="maintenance",
        ),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    updated = await OrderUpdateCommandService.update_order_for_manager(
        command_session, created["id"],
        ManagerOrderUpdatePayload(workflow_type="service_work", service_type=None),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    order = await command_session.get(Order, created["id"])
    assert updated["workflow_type"] == "service_work"
    assert "service_type" not in order.technical_meta


@pytest.mark.asyncio
async def test_explicit_repair_selection_initializes_state_without_paid_line(
    command_session, monkeypatch,
):
    async def unexpected_paid_diagnostic(*args, **kwargs):
        raise AssertionError("Scenario choice must not add a paid service")

    monkeypatch.setattr(OrderService, "_maybe_add_default_repair_diagnostic", unexpected_paid_diagnostic)
    customer = Customer(tenant_id=1, name="Клиент", phone="")
    command_session.add(customer)
    await command_session.commit()
    created = await OrderCreateCommandService.create_manager_order(
        command_session,
        ManagerOrderCreatePayload(
            source="manager", customer_id=customer.id,
            workflow_type="repair", service_type="repair",
        ),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert created["workflow_type"] == "repair"
    assert created["repair_meta"]["repair_status"] == "new"
    await OrderUpdateCommandService.update_order_for_manager(
        command_session, created["id"],
        ManagerOrderUpdatePayload(workflow_type="service_work", service_type=None),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    updated = await OrderUpdateCommandService.update_order_for_manager(
        command_session, created["id"],
        ManagerOrderUpdatePayload(workflow_type="repair", service_type="repair"),
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert updated["repair_meta"]["repair_status"] == "new"


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
