from datetime import datetime, timedelta
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
import pytest

from core.config import settings
from core.database import get_session
from crud.product import ProductDAO
from main import app
from models import Customer, LeadSource, Order, OrderStatus, Product
from schemas import (
    ProductAvailabilityLeadPayload,
    ProductAvailabilityLeadResponse,
    PublicContactLeadPayload,
    PublicContactLeadResponse,
)
from services.bot_service import BotService
from services.lead_service import LeadService
from services.order_service import OrderService
from services.staff_user_service import StaffUserService
from services.website_lead_service import WebsiteLeadService


@pytest.mark.asyncio
async def test_create_contact_lead_uses_lead_funnel_and_notifies_all_owners(monkeypatch):
    created_at = datetime.now()
    captured = {}
    messages = []

    async def fake_create_lead(_session, payload):
        captured["payload"] = payload
        return {"id": 33, "status": "new", "created_at": created_at}

    async def fake_recipients(_session):
        return [1001, 1002]

    async def fake_send_message(admin_id, text):
        messages.append((admin_id, text))
        return True

    monkeypatch.setattr(LeadService, "create_lead", fake_create_lead)
    monkeypatch.setattr(
        StaffUserService,
        "get_active_owner_admin_telegram_recipient_ids",
        fake_recipients,
    )
    monkeypatch.setattr(BotService, "send_message", fake_send_message)

    response = await WebsiteLeadService.create_contact_lead(
        object(),
        PublicContactLeadPayload(
            name="Иван <b>",
            phone="+375 (29) 111-22-33",
            address="Минск",
            message="Нужен монтаж <script>",
        ),
    )

    assert response == PublicContactLeadResponse(
        lead_id=33,
        status="new",
        created_at=created_at,
    )
    assert captured["payload"].source == "site"
    assert "Адрес/район: Минск" in captured["payload"].request_text
    assert [admin_id for admin_id, _text in messages] == [1001, 1002]
    assert "&lt;b&gt;" in messages[0][1]
    assert "&lt;script&gt;" in messages[0][1]


@pytest.mark.asyncio
async def test_public_contact_lead_endpoint_uses_dedicated_lead_contract(monkeypatch):
    async def override_get_session():
        yield object()

    async def fake_create(_session, payload):
        assert payload.name == "Иван"
        return PublicContactLeadResponse(
            lead_id=34,
            status="new",
            created_at=datetime.now(),
        )

    monkeypatch.setattr(WebsiteLeadService, "create_contact_lead", fake_create)
    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/leads/contact",
                json={
                    "name": "Иван",
                    "phone": "+375 (29) 111-22-33",
                    "address": "Минск",
                    "message": "Нужна консультация",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["lead_id"] == 34


@pytest.mark.asyncio
async def test_create_product_availability_request_creates_site_order_and_notifies_admins(monkeypatch):
    product = Product(
        id=7,
        title="TCL BreezeIN",
        slug="tcl-breezein",
        price=3200,
        specs={"area_m2": 35},
        is_published=True,
    )
    order = Order(
        id=91,
        status=OrderStatus.NEW_LEAD,
        lead_source=LeadSource.SITE,
        created_at=datetime.now(),
        technical_meta={},
    )
    fake_session = SimpleNamespace(commit_calls=0, add=lambda *_args, **_kwargs: None)
    sent_messages = []

    async def fake_get_by_id(_session, product_id):
        assert product_id == product.id
        return product

    async def fake_find_recent(*args, **kwargs):
        return None

    async def fake_create_from_website(**kwargs):
        assert kwargs["items"] == []
        assert kwargs["lead_source"] == LeadSource.SITE
        assert "Сообщить о поступлении" in (kwargs["comment"] or "")
        return order

    async def fake_send_message(admin_id, text):
        sent_messages.append((admin_id, text))
        return True

    async def fake_commit():
        fake_session.commit_calls += 1

    async def fake_refresh(*_args, **_kwargs):
        return None

    fake_session.commit = fake_commit
    fake_session.refresh = fake_refresh

    monkeypatch.setattr(ProductDAO, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(WebsiteLeadService, "_find_recent_product_availability_order", fake_find_recent)
    monkeypatch.setattr(OrderService, "create_from_website", fake_create_from_website)
    monkeypatch.setattr(BotService, "send_message", fake_send_message)
    monkeypatch.setattr(settings, "ADMIN_IDS", "1001,1002")
    monkeypatch.setattr(settings, "ADMIN_ID", 0)

    response = await WebsiteLeadService.create_product_availability_lead(
        fake_session,
        ProductAvailabilityLeadPayload(
            product_id=product.id,
            phone="+375 (29) 111-22-33",
            name="Иван",
        ),
    )

    assert response.lead_id == 91
    assert response.status == "new_lead"
    assert order.technical_meta["availability_product_id"] == product.id
    assert "availability_last_requested_at" in order.technical_meta
    assert "availability_last_notified_at" in order.technical_meta
    assert fake_session.commit_calls == 2
    assert len(sent_messages) == 2
    assert "Заявка #91" in sent_messages[0][1]
    assert "tcl-breezein" in sent_messages[0][1]


@pytest.mark.asyncio
async def test_create_product_availability_request_reuses_recent_duplicate_without_notify(monkeypatch):
    product = Product(
        id=7,
        title="TCL BreezeIN",
        slug="tcl-breezein",
        price=3200,
        specs={"area_m2": 35},
        is_published=True,
    )
    customer = Customer(name="Старое имя", phone="+375 (29) 111-22-33")
    existing_order = Order(
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
    sent_messages = []

    async def fake_get_by_id(_session, product_id):
        assert product_id == product.id
        return product

    async def fake_find_recent(**kwargs):
        return existing_order

    async def fake_commit():
        fake_session.commit_calls += 1

    async def fake_refresh(*_args, **_kwargs):
        return None

    async def fake_send_message(admin_id, text):
        sent_messages.append((admin_id, text))
        return True

    fake_session.commit = fake_commit
    fake_session.refresh = fake_refresh

    monkeypatch.setattr(ProductDAO, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(WebsiteLeadService, "_find_recent_product_availability_order", fake_find_recent)
    monkeypatch.setattr(BotService, "send_message", fake_send_message)
    monkeypatch.setattr(settings, "ADMIN_IDS", "1001")
    monkeypatch.setattr(settings, "ADMIN_ID", 0)

    response = await WebsiteLeadService.create_product_availability_lead(
        fake_session,
        ProductAvailabilityLeadPayload(
            product_id=product.id,
            phone="+375 (29) 111-22-33",
            name="Иван",
        ),
    )

    assert response.lead_id == 91
    assert response.status == "new_lead"
    assert existing_order.customer.name == "Иван"
    assert existing_order.comment == WebsiteLeadService._build_request_text(product)
    assert fake_session.commit_calls == 1
    assert sent_messages == []


@pytest.mark.asyncio
async def test_create_product_availability_request_reuses_duplicate_and_notifies_after_cooldown(monkeypatch):
    product = Product(
        id=7,
        title="TCL BreezeIN",
        slug="tcl-breezein",
        price=3200,
        specs={"area_m2": 35},
        is_published=True,
    )
    customer = Customer(name="Старое имя", phone="+375 (29) 111-22-33")
    existing_order = Order(
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
    sent_messages = []

    async def fake_get_by_id(_session, product_id):
        assert product_id == product.id
        return product

    async def fake_find_recent(**kwargs):
        return existing_order

    async def fake_commit():
        fake_session.commit_calls += 1

    async def fake_refresh(*_args, **_kwargs):
        return None

    async def fake_send_message(admin_id, text):
        sent_messages.append((admin_id, text))
        return True

    fake_session.commit = fake_commit
    fake_session.refresh = fake_refresh

    monkeypatch.setattr(ProductDAO, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(WebsiteLeadService, "_find_recent_product_availability_order", fake_find_recent)
    monkeypatch.setattr(BotService, "send_message", fake_send_message)
    monkeypatch.setattr(settings, "ADMIN_IDS", "1001")
    monkeypatch.setattr(settings, "ADMIN_ID", 0)

    response = await WebsiteLeadService.create_product_availability_lead(
        fake_session,
        ProductAvailabilityLeadPayload(
            product_id=product.id,
            phone="+375 (29) 111-22-33",
            name="Иван",
        ),
    )

    assert response.lead_id == 92
    assert existing_order.status == OrderStatus.NEW_LEAD
    assert existing_order.closing_result is None
    assert existing_order.closed_at is None
    assert fake_session.commit_calls == 2
    assert len(sent_messages) == 1
    assert "ПОВТОРНЫЙ ЗАПРОС" in sent_messages[0][1]


@pytest.mark.asyncio
async def test_public_product_availability_lead_endpoint_returns_response(monkeypatch):
    async def override_get_session():
        yield object()

    async def fake_create(_session, payload):
        assert payload.product_id == 7
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
async def test_public_product_availability_lead_endpoint_validates_phone():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/leads/product-availability",
            json={
                "product_id": 7,
                "phone": "12345",
            },
        )

    assert response.status_code == 422
