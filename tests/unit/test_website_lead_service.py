from datetime import datetime, timedelta
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
import pytest

from core.database import get_session
from core.tenant_scope import get_public_tenant_scope
from crud.product import ProductDAO
from main import app
from models import Customer, Lead, LeadSource, Order, OrderStatus, Product
from schemas import (
    ProductAvailabilityLeadPayload,
    ProductAvailabilityLeadResponse,
    PublicContactLeadPayload,
    PublicContactLeadResponse,
)
from services.communications.tenant_website_event_service import (
    TenantWebsiteEventService,
)
from services.lead_service import LeadService
from services.order_service import OrderService
from services.public_write_idempotency_service import PublicWriteIdempotencyService
from services.website_lead_service import WebsiteLeadService


async def _execute_once(session, *, operation, **_kwargs):
    result = await operation()
    commit = getattr(session, "commit", None)
    if commit is not None:
        await commit()
    return SimpleNamespace(value=result.value, replayed=False)


@pytest.mark.asyncio
async def test_create_contact_lead_uses_lead_funnel_and_enqueues_event(
    monkeypatch,
    tenant_scope,
):
    created_at = datetime.now()
    captured = {}

    async def fake_create_lead(_session, payload, *, tenant_scope):
        captured["payload"] = payload
        captured["tenant_scope"] = tenant_scope
        return {"id": 33, "status": "new", "created_at": created_at}

    async def fake_enqueue(_session, **kwargs):
        captured["event"] = kwargs

    monkeypatch.setattr(LeadService, "create_lead", fake_create_lead)
    monkeypatch.setattr(
        TenantWebsiteEventService,
        "enqueue_contact_lead",
        fake_enqueue,
    )
    monkeypatch.setattr(PublicWriteIdempotencyService, "execute", _execute_once)

    response = await WebsiteLeadService.create_contact_lead(
        object(),
        PublicContactLeadPayload(
            name="Иван <b>",
            phone="+375 (29) 111-22-33",
            address="Минск",
            message="Нужен монтаж <script>",
        ),
        tenant_scope=tenant_scope,
        idempotency_key="contact-request-unit-0001",
    )

    assert response == PublicContactLeadResponse(
        lead_id=33,
        status="new",
        created_at=created_at,
    )
    assert captured["payload"].source == "site"
    assert captured["tenant_scope"] == tenant_scope
    assert "Адрес/район: Минск" in captured["payload"].request_text
    assert captured["event"]["lead_id"] == 33
    assert captured["event"]["name"] == "Иван <b>"
    assert captured["event"]["message"] == "Нужен монтаж <script>"
    assert captured["event"]["tenant_scope"] == tenant_scope
    assert len(captured["event"]["request_key_hash"]) == 64


@pytest.mark.asyncio
async def test_public_contact_lead_endpoint_uses_dedicated_lead_contract(
    async_client,
    db,
):
    response = await async_client.post(
        "/api/v1/leads/contact",
        json={
            "name": "Иван",
            "phone": "+375 (29) 111-22-33",
            "address": "Минск",
            "message": "Нужна консультация",
        },
    )

    assert response.status_code == 200
    lead = await db.get(Lead, response.json()["lead_id"])
    assert lead is not None
    assert lead.tenant_id == 1
    assert lead.storefront_id == 1


@pytest.mark.asyncio
async def test_create_product_availability_request_enqueues_with_single_commit(
    monkeypatch,
    tenant_scope,
):
    product = Product(
        id=7,
        title="TCL BreezeIN",
        slug="tcl-breezein",
        price=3200,
        specs={"area_m2": 35},
        is_published=True,
    )
    order = Order(
        tenant_id=1,
        storefront_id=1,
        id=91,
        status=OrderStatus.NEW_LEAD,
        lead_source=LeadSource.SITE,
        created_at=datetime.now(),
        technical_meta={},
    )
    fake_session = SimpleNamespace(commit_calls=0, add=lambda *_args, **_kwargs: None)
    enqueued = []

    async def fake_get_by_id(_session, product_id):
        assert product_id == product.id
        return product

    async def fake_find_recent(*args, **kwargs):
        return None

    async def fake_create_from_website(**kwargs):
        assert kwargs["items"] == []
        assert kwargs["lead_source"] == LeadSource.SITE
        assert "Сообщить о поступлении" in (kwargs["comment"] or "")
        assert kwargs["tenant_scope"] == tenant_scope
        return order

    async def fake_enqueue(_session, **kwargs):
        enqueued.append(kwargs)

    async def fake_commit():
        fake_session.commit_calls += 1

    async def fake_refresh(*_args, **_kwargs):
        return None

    fake_session.commit = fake_commit
    fake_session.refresh = fake_refresh

    monkeypatch.setattr(ProductDAO, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(WebsiteLeadService, "_find_recent_product_availability_order", fake_find_recent)
    monkeypatch.setattr(OrderService, "create_from_website", fake_create_from_website)
    monkeypatch.setattr(TenantWebsiteEventService, "enqueue_availability", fake_enqueue)
    monkeypatch.setattr(PublicWriteIdempotencyService, "execute", _execute_once)

    response = await WebsiteLeadService.create_product_availability_lead(
        fake_session,
        ProductAvailabilityLeadPayload(
            product_id=product.id,
            phone="+375 (29) 111-22-33",
            name="Иван",
        ),
        tenant_scope=tenant_scope,
        idempotency_key="availability-request-unit-0001",
    )

    assert response.lead_id == 91
    assert response.status == "new_lead"
    assert order.technical_meta["availability_product_id"] == product.id
    assert "availability_last_requested_at" in order.technical_meta
    assert "availability_last_notified_at" in order.technical_meta
    assert fake_session.commit_calls == 1
    assert len(enqueued) == 1
    assert enqueued[0]["order"] is order
    assert enqueued[0]["product"] is product
    assert enqueued[0]["is_repeat"] is False
    assert enqueued[0]["tenant_scope"] == tenant_scope


@pytest.mark.asyncio
async def test_create_product_availability_request_reuses_recent_duplicate_without_notify(
    monkeypatch,
    tenant_scope,
):
    product = Product(
        id=7,
        title="TCL BreezeIN",
        slug="tcl-breezein",
        price=3200,
        specs={"area_m2": 35},
        is_published=True,
    )
    customer = Customer(tenant_id=1, name="Старое имя", phone="+375 (29) 111-22-33")
    existing_order = Order(
        tenant_id=1,
        storefront_id=1,
        id=91,
        status=OrderStatus.NEW_LEAD,
        lead_source=LeadSource.SITE,
        created_at=datetime.now(),
        technical_meta={
            "availability_product_id": product.id,
            "availability_last_notified_at": datetime.now().isoformat(),
        },
    )
    existing_order.customer = customer
    fake_session = SimpleNamespace(commit_calls=0, add=lambda *_args, **_kwargs: None)

    async def fake_get_by_id(_session, product_id):
        assert product_id == product.id
        return product

    async def fake_find_recent(**kwargs):
        return existing_order

    async def fake_commit():
        fake_session.commit_calls += 1

    async def fake_refresh(*_args, **_kwargs):
        return None

    async def must_not_enqueue(*_args, **_kwargs):
        raise AssertionError("availability cooldown repeated event enqueue")

    fake_session.commit = fake_commit
    fake_session.refresh = fake_refresh

    monkeypatch.setattr(ProductDAO, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(WebsiteLeadService, "_find_recent_product_availability_order", fake_find_recent)
    monkeypatch.setattr(
        TenantWebsiteEventService,
        "enqueue_availability",
        must_not_enqueue,
    )
    monkeypatch.setattr(PublicWriteIdempotencyService, "execute", _execute_once)

    response = await WebsiteLeadService.create_product_availability_lead(
        fake_session,
        ProductAvailabilityLeadPayload(
            product_id=product.id,
            phone="+375 (29) 111-22-33",
            name="Иван",
        ),
        tenant_scope=tenant_scope,
        idempotency_key="availability-request-unit-0002",
    )

    assert response.lead_id == 91
    assert response.status == "new_lead"
    assert existing_order.customer.name == "Иван"
    assert existing_order.comment == WebsiteLeadService._build_request_text(product)
    assert fake_session.commit_calls == 1


@pytest.mark.asyncio
async def test_create_product_availability_request_reuses_duplicate_and_notifies_after_cooldown(
    monkeypatch,
    tenant_scope,
):
    product = Product(
        id=7,
        title="TCL BreezeIN",
        slug="tcl-breezein",
        price=3200,
        specs={"area_m2": 35},
        is_published=True,
    )
    customer = Customer(tenant_id=1, name="Старое имя", phone="+375 (29) 111-22-33")
    existing_order = Order(
        tenant_id=1,
        storefront_id=1,
        id=92,
        status=OrderStatus.CLOSED,
        lead_source=LeadSource.SITE,
        created_at=datetime.now() - timedelta(days=2),
        closed_at=datetime.now() - timedelta(days=1),
        technical_meta={
            "availability_product_id": product.id,
            "availability_last_notified_at": (datetime.now() - timedelta(days=2)).isoformat(),
        },
    )
    existing_order.customer = customer
    existing_order.closing_result = "lost"
    fake_session = SimpleNamespace(commit_calls=0, add=lambda *_args, **_kwargs: None)
    enqueued = []

    async def fake_get_by_id(_session, product_id):
        assert product_id == product.id
        return product

    async def fake_find_recent(**kwargs):
        return existing_order

    async def fake_commit():
        fake_session.commit_calls += 1

    async def fake_refresh(*_args, **_kwargs):
        return None

    async def fake_enqueue(_session, **kwargs):
        enqueued.append(kwargs)

    fake_session.commit = fake_commit
    fake_session.refresh = fake_refresh

    monkeypatch.setattr(ProductDAO, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(WebsiteLeadService, "_find_recent_product_availability_order", fake_find_recent)
    monkeypatch.setattr(TenantWebsiteEventService, "enqueue_availability", fake_enqueue)
    monkeypatch.setattr(PublicWriteIdempotencyService, "execute", _execute_once)

    response = await WebsiteLeadService.create_product_availability_lead(
        fake_session,
        ProductAvailabilityLeadPayload(
            product_id=product.id,
            phone="+375 (29) 111-22-33",
            name="Иван",
        ),
        tenant_scope=tenant_scope,
        idempotency_key="availability-request-unit-0003",
    )

    assert response.lead_id == 92
    assert existing_order.status == OrderStatus.NEW_LEAD
    assert existing_order.closing_result is None
    assert existing_order.closed_at is None
    assert fake_session.commit_calls == 1
    assert len(enqueued) == 1
    assert enqueued[0]["order"] is existing_order
    assert enqueued[0]["is_repeat"] is True


@pytest.mark.asyncio
async def test_public_product_availability_lead_endpoint_returns_response(
    monkeypatch,
    tenant_scope,
):
    async def override_get_session():
        yield object()

    async def override_tenant_scope():
        return tenant_scope

    async def fake_create(_session, payload, *, tenant_scope, idempotency_key):
        assert payload.product_id == 7
        assert tenant_scope.tenant_id == 1
        assert tenant_scope.storefront_id == 1
        assert idempotency_key
        return ProductAvailabilityLeadResponse(
            lead_id=12,
            status="new_lead",
            created_at=datetime.now(),
        )

    monkeypatch.setattr(
        WebsiteLeadService,
        "create_product_availability_lead",
        fake_create,
    )
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_public_tenant_scope] = override_tenant_scope

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/leads/product-availability",
                json={
                    "product_id": 7,
                    "phone": "+375 (29) 111-22-33",
                    "name": "Иван",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["lead_id"] == 12


@pytest.mark.asyncio
async def test_public_product_availability_lead_endpoint_validates_phone(tenant_scope):
    async def override_tenant_scope():
        return tenant_scope

    app.dependency_overrides[get_public_tenant_scope] = override_tenant_scope
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/leads/product-availability",
                json={
                    "product_id": 7,
                    "phone": "12345",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
