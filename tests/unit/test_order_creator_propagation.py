"""Trusted creation identity is optional, scoped, and never reapplied on replay."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from models import (Customer, Lead, LegacyOwnerAuthState, Order, OrderStatus,
                    StaffUser, Storefront, Tenant, TenantMembership)
from models.tenancy import TenantScope
from schemas import LeadQualifyPayload, ManagerOrderCreatePayload
from services.order_create_command_service import OrderCreateCommandService
from services.order_responsibility_service import OrderResponsibilityService


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def creator_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'creators.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([
            Tenant(id=1, slug="mvn", display_name="MVN", is_system=True),
            Storefront(id=1, tenant_id=1, slug="main", display_name="Main", is_default=True, status="active"),
            LegacyOwnerAuthState(),
            StaffUser(id=11, display_name="Manager", username="manager", roles=["manager"], primary_role="manager"),
            StaffUser(id=12, display_name="Other manager", roles=["manager"], primary_role="manager"),
            StaffUser(id=13, display_name="Editor", roles=["catalog_editor"], primary_role="catalog_editor"),
            StaffUser(id=14, display_name="Platform support", roles=["owner"], primary_role="owner"),
        ])
        await session.flush()
        session.add_all([TenantMembership(tenant_id=1, staff_user_id=staff_id, role=role)
                         for staff_id, role in [(11, "manager"), (12, "manager"), (13, "catalog_editor")]])
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.parametrize("creator,expected", [(11, 11), (13, None), (14, None), (None, None)])
async def test_manager_creation_uses_actual_eligible_membership_only(creator_session, creator, expected):
    # Source/username-like fields cannot manufacture creator authority.
    payload = ManagerOrderCreatePayload(name="manager", source="bot", request_text="New order")
    result = await OrderCreateCommandService.create_manager_order(
        creator_session, payload, tenant_scope=SCOPE, creator_staff_user_id=creator,
    )
    order = await creator_session.get(Order, result["id"])
    assert order.responsible_staff_user_id == expected
    assert order.responsible_version == 0


async def test_manager_creation_fences_before_first_customer_flush_and_preserves_reassignment_on_retry(
    creator_session, monkeypatch,
):
    fenced = False
    initial = OrderResponsibilityService.initial_responsible

    async def fence(*args):
        nonlocal fenced
        result = await initial(*args)
        fenced = True
        return result

    def before_flush(*_):
        assert fenced, "creator parent locks must precede Customer/Order persistence"

    monkeypatch.setattr(OrderResponsibilityService, "initial_responsible", fence)
    event.listen(creator_session.sync_session, "before_flush", before_flush)
    payload = ManagerOrderCreatePayload(source="manager", name="New customer", request_text="New", client_request_id=uuid4())
    first = await OrderCreateCommandService.create_manager_order(
        creator_session, payload, tenant_scope=SCOPE, creator_staff_user_id=11,
    )
    order = await creator_session.get(Order, first["id"])
    order.responsible_staff_user_id = 12
    order.responsible_version = 1
    await creator_session.commit()
    repeated = await OrderCreateCommandService.create_manager_order(
        creator_session, payload, tenant_scope=SCOPE, creator_staff_user_id=13,
    )
    assert repeated["id"] == first["id"]
    assert (order.responsible_staff_user_id, order.responsible_version) == (12, 1)


async def test_manager_route_uses_verified_actor_and_has_no_creator_payload_field(monkeypatch):
    from core.security import AuthenticatedUser
    from routers.manager_orders_write import create_manager_order

    create = AsyncMock(return_value={"id": 7})
    monkeypatch.setattr(OrderCreateCommandService, "create_manager_order", create)
    assert "creator_staff_user_id" not in ManagerOrderCreatePayload.model_fields
    payload = ManagerOrderCreatePayload.model_validate({
        "source": "manager", "name": "other", "request_text": "Request",
        "creator_staff_user_id": 13, "responsible_staff_user_id": 13,
    })
    await create_manager_order(
        payload,
        auth=AuthenticatedUser(username="verified", staff_user_id=11, auth_source="staff", role="manager"),
        session=object(), tenant_scope=SCOPE,
    )
    assert create.await_args.kwargs["creator_staff_user_id"] == 11


async def test_public_order_factory_keeps_responsible_unset(creator_session, monkeypatch):
    from services.order_service import OrderService

    allocation = AsyncMock(side_effect=AssertionError("public intake has no verified staff creator"))
    monkeypatch.setattr(OrderResponsibilityService, "initial_responsible", allocation)
    order = await OrderService.create_from_website(
        creator_session, tenant_scope=SCOPE, customer_name="manager", customer_phone="",
        customer_email=None, customer_address=None, items=[], commit=False,
    )
    await creator_session.commit()
    assert order.responsible_staff_user_id is None
    allocation.assert_not_awaited()


async def test_qualified_lead_assigns_once_and_keeps_manual_responsible(creator_session):
    from services.lead_command_service import LeadCommandService

    lead = Lead(tenant_id=1, storefront_id=1, name="Lead", request_text="New")
    creator_session.add(lead)
    await creator_session.commit()
    payload = LeadQualifyPayload(name="Customer", customer_type="individual", workflow_type="maintenance")
    first = await LeadCommandService.qualify_lead(
        creator_session, lead.id, payload, tenant_scope=SCOPE, creator_staff_user_id=11,
    )
    order = await creator_session.get(Order, first["order_id"])
    assert order.responsible_staff_user_id == 11
    order.responsible_staff_user_id = 12
    await creator_session.commit()
    repeated = await LeadCommandService.qualify_lead(
        creator_session, lead.id, payload, tenant_scope=SCOPE, creator_staff_user_id=11,
    )
    assert repeated["order_id"] == order.id
    assert order.responsible_staff_user_id == 12


@pytest.mark.parametrize("existing_customer", [False, True])
async def test_bot_both_customer_branches_assign_live_creator_before_first_flush(
    creator_session, monkeypatch, existing_customer,
):
    from services.bot_quick_order_service import BotQuickOrderService

    draft = {"name": "New customer", "customer_type": "individual", "workflow_type": "maintenance", "request_text": "Service"}
    if existing_customer:
        customer = Customer(tenant_id=1, name="Existing", phone="")
        creator_session.add(customer)
        await creator_session.commit()
        draft["customer_id"] = customer.id
    fenced = False
    initial = OrderResponsibilityService.initial_responsible

    async def fence(*args):
        nonlocal fenced
        result = await initial(*args)
        fenced = True
        return result

    def before_flush(*_):
        assert fenced, "new Lead/Customer/Order must follow the creator fence"

    monkeypatch.setattr(OrderResponsibilityService, "initial_responsible", fence)
    monkeypatch.setattr("services.bot_quick_order_service.NotificationService.notify_admins_staff_order_created", AsyncMock())
    event.listen(creator_session.sync_session, "before_flush", before_flush)
    result = await BotQuickOrderService.create_order_from_draft(
        creator_session, draft, tenant_scope=SCOPE, creator_staff_user_id=11, source_fingerprint="bot:one",
    )
    order = await creator_session.get(Order, result["id"])
    assert order.responsible_staff_user_id == 11


async def test_bot_api_takes_creator_from_live_context_not_draft(monkeypatch):
    from api_contracts.bot import BotQuickOrderDraft
    from services.bot_quick_order_api_service import BotQuickOrderApiService

    create = AsyncMock(return_value={"id": 7, "customer_id": 3})
    monkeypatch.setattr(BotQuickOrderApiService, "_require_manager", AsyncMock(return_value=SimpleNamespace(staff_user_id=11)))
    monkeypatch.setattr("services.bot_quick_order_api_service.resolve_bot_scope", AsyncMock(return_value=SCOPE))
    monkeypatch.setattr("services.bot_quick_order_api_service.BotQuickOrderService.create_order_from_draft", create)
    await BotQuickOrderApiService._create_locked(
        object(), telegram_id=101, source_fingerprint="bot:1", draft=BotQuickOrderDraft(request_text="New", service_label="Service"),
    )
    assert create.await_args.kwargs["creator_staff_user_id"] == 11


async def test_maintenance_workspace_assigns_new_continuation_only(creator_session):
    from services.maintenance_offer_service import MaintenanceOfferService

    customer = Customer(tenant_id=1, name="Customer", phone="")
    creator_session.add(customer)
    await creator_session.flush()
    source = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, workflow_type="maintenance", status=OrderStatus.CLOSED)
    creator_session.add(source)
    await creator_session.commit()
    result = await MaintenanceOfferService.workspace(
        creator_session, source_order_id=source.id, scope=SCOPE, actor="audit", creator_staff_user_id=11,
    )
    order = await creator_session.get(Order, result["continuation_order_id"])
    assert order.responsible_staff_user_id == 11
    order.responsible_staff_user_id = 12
    await creator_session.commit()
    repeated = await MaintenanceOfferService.workspace(
        creator_session, source_order_id=source.id, scope=SCOPE, actor="audit", creator_staff_user_id=11,
    )
    assert repeated == result
    assert order.responsible_staff_user_id == 12


async def test_catalog_quick_order_assigns_creator_and_keeps_replayed_assignment(creator_session, monkeypatch):
    from services.catalog_decision_quick_order_service import CatalogDecisionQuickOrderService

    monkeypatch.setattr("services.catalog_decision_quick_order_service.CatalogDecisionQueryService.get_product_snapshots",
                        AsyncMock(return_value={}))
    first = await CatalogDecisionQuickOrderService.create(
        creator_session, product_ids=[], idempotency_key="catalog:one", prospect_type="individual",
        tenant_scope=SCOPE, creator_staff_user_id=11,
    )
    order = await creator_session.get(Order, first["id"])
    assert order.responsible_staff_user_id == 11
    order.responsible_staff_user_id = 12
    await creator_session.commit()
    repeated = await CatalogDecisionQuickOrderService.create(
        creator_session, product_ids=[], idempotency_key="catalog:one", prospect_type="individual",
        tenant_scope=SCOPE, creator_staff_user_id=11,
    )
    assert repeated["id"] == first["id"]
    assert order.responsible_staff_user_id == 12


async def test_equipment_maintenance_creation_propagates_creator(creator_session):
    from models import CustomerEquipment
    from services.equipment_service import EquipmentService

    customer = Customer(tenant_id=1, name="Customer", phone="")
    creator_session.add(customer)
    await creator_session.flush()
    equipment = CustomerEquipment(customer_id=customer.id, display_name="Air conditioner")
    creator_session.add(equipment)
    await creator_session.commit()
    result = await EquipmentService.create_maintenance_order(
        creator_session, equipment_id=equipment.id, tenant_scope=SCOPE, creator_staff_user_id=11,
    )
    order = await creator_session.get(Order, result["id"])
    assert order.responsible_staff_user_id == 11


async def test_native_act_assigns_only_new_continuation(creator_session, monkeypatch):
    from api_contracts.maintenance_observations import CreateMaintenanceObservation, PrepareMaintenanceDefectAct
    from datetime import datetime, timezone
    from models import DocumentLegalEntity
    from modules.documents.application.maintenance_act_preparation import MaintenanceActPreparationService
    from services.maintenance_observation_service import MaintenanceObservationService

    customer = Customer(tenant_id=1, name="Customer", phone="")
    issuer = DocumentLegalEntity(tenant_id=1, slug="issuer", display_name="Issuer", legal_name="Issuer", unp="123456789")
    creator_session.add_all([customer, issuer])
    await creator_session.flush()
    source = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, workflow_type="maintenance", status=OrderStatus.CLOSED)
    creator_session.add(source)
    await creator_session.commit()
    finding = await MaintenanceObservationService.create(
        creator_session, order_id=source.id, scope=SCOPE, actor="audit", payload=CreateMaintenanceObservation(
            command_key=uuid4(), equipment_description="Unit", facts="Leak", recommendation="Repair",
            original_comment="Leak", observed_at=datetime.now(timezone.utc),
        ),
    )
    # Document template/storage behavior is covered by its own suite. Keep real
    # transaction, continuation and preparation writes in this allocation test.
    monkeypatch.setattr(MaintenanceActPreparationService, "template", AsyncMock(return_value=1))
    monkeypatch.setattr("modules.documents.application.maintenance_act_preparation.ManagedDocumentService.create_draft",
                        AsyncMock(return_value=SimpleNamespace(id=None)))

    async def item(session, preparation, continuation, scope):
        return {"continuation_order_id": continuation.order_id}

    monkeypatch.setattr(MaintenanceActPreparationService, "item", item)
    for expected in [11, 12]:
        result = await MaintenanceActPreparationService.prepare(
            creator_session, source_order_id=source.id, scope=SCOPE, actor="audit", storage=object(),
            creator_staff_user_id=11, payload=PrepareMaintenanceDefectAct(
                command_key=uuid4(), legal_entity_id=issuer.id, issue_date="2026-10-16",
                observations=[{"observation_id": finding.id, "expected_version": 1}],
            ),
        )
        order = await creator_session.get(Order, result["continuation_order_id"])
        assert order.responsible_staff_user_id == expected
        order.responsible_staff_user_id = 12
        await creator_session.commit()


async def test_connector_fences_before_receipt_and_passes_verified_staff_to_act(monkeypatch):
    from schemas_connector_maintenance import DefectActPrepareInput
    from services.connector_maintenance_service import ConnectorMaintenanceService
    from modules.documents.application.maintenance_act_preparation import MaintenanceActPreparationService

    calls = []

    async def fence(session, scope, creator):
        assert creator == 11 and scope == SCOPE
        calls.append("fence")
        return creator

    async def execute(session, **kwargs):
        calls.append("receipt")
        return await kwargs["operation"]()

    async def prepare(session, **kwargs):
        assert kwargs["creator_staff_user_id"] == 11
        assert kwargs["actor"] == "audit-name-only"
        calls.append("domain")
        raise RuntimeError("stop before document IO")

    monkeypatch.setattr(OrderResponsibilityService, "initial_responsible", fence)
    monkeypatch.setattr("services.connector_maintenance_service.Offers.context", AsyncMock())
    monkeypatch.setattr("services.connector_maintenance_service.AuthenticatedCommandService.execute", execute)
    monkeypatch.setattr(MaintenanceActPreparationService, "prepare", prepare)
    inputs = DefectActPrepareInput(order_id=1, idempotency_key="creator-test-key-0001", payload={
        "observations": [{"observation_id": 1, "expected_version": 1}], "legal_entity_id": 1, "issue_date": "2026-10-16",
    })
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(tenant_id=1, status="active")))
    actor = SimpleNamespace(tenant_scope=SCOPE, staff_user_id=11, username="audit-name-only")
    with pytest.raises(RuntimeError, match="stop before document IO"):
        await ConnectorMaintenanceService.write(session, actor, "prepare_maintenance_defect_act", inputs)
    assert calls == ["fence", "receipt", "domain"]
