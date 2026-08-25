from datetime import datetime
from types import SimpleNamespace

import pytest

from models import LeadSource, OrderStatus
from schemas import OrderPayload
from services.communications.tenant_website_event_service import (
    TenantWebsiteEventService,
)
from services.installation_pricing_service import (
    InstallationPricingError,
    InstallationPricingService,
)
from services.order_product_link_command import (
    OrderProductCatalogSnapshot,
    OrderProductLinkCommand,
)
from services.order_service import OrderService
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from services.public_write_idempotency_service import PublicWriteIdempotencyService
from services.website_order_service import WebsiteOrderService


async def _execute_once(session, *, operation, **_kwargs):
    result = await operation()
    commit = getattr(session, "commit", None)
    if commit is not None:
        await commit()
    return SimpleNamespace(value=result.value, replayed=False)


@pytest.mark.asyncio
async def test_website_checkout_creates_negotiation_order(monkeypatch, tenant_scope):
    captured_kwargs = {}
    captured_event = {}
    session = SimpleNamespace(commit_calls=0)

    async def commit():
        session.commit_calls += 1

    session.commit = commit

    async def fake_create_from_website(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            id=55,
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            status=OrderStatus.NEGOTIATION,
            total_amount=3456,
            created_at=datetime.now(),
        )

    async def fake_enqueue(event_session, **kwargs):
        captured_event["session"] = event_session
        captured_event.update(kwargs)

    async def fake_price_items(_session, items, *, catalog_snapshots):
        assert catalog_snapshots[7].unit_price == 3000
        return [item.model_dump() for item in items]

    async def fake_checkout_snapshots(_session, *, tenant_scope, product_ids):
        assert tenant_scope is not None
        assert product_ids == {7}
        return {
            7: OrderProductCatalogSnapshot(
                product_id=7,
                title="Checkout title",
                unit_price=3000,
                currency="BYN",
                pricing_source="shared_product",
            )
        }

    monkeypatch.setattr(OrderService, "create_from_website", fake_create_from_website)
    monkeypatch.setattr(
        InstallationPricingService, "price_public_items", fake_price_items
    )
    monkeypatch.setattr(
        PublicCatalogVisibilityService,
        "get_checkout_snapshots",
        fake_checkout_snapshots,
    )
    monkeypatch.setattr(TenantWebsiteEventService, "enqueue_checkout", fake_enqueue)
    monkeypatch.setattr(PublicWriteIdempotencyService, "execute", _execute_once)

    payload = OrderPayload.model_validate(
        {
            "customer": {
                "name": "Тестовый клиент",
                "phone": "+375291112233",
                "email": "checkout@example.com",
                "address": "г. Минск, ул. Тестовая 10",
            },
            "items": [
                {
                    "product_id": 7,
                    "quantity": 1,
                    "with_installation": True,
                    "installation_price": 280,
                    "installation_meta": {"source": "web"},
                    "installation_options": ["standard"],
                }
            ],
            "comment": "Нужен монтаж",
        }
    )

    response = await WebsiteOrderService.create_order(
        session,
        payload,
        tenant_scope=tenant_scope,
        idempotency_key="checkout-request-unit-0001",
    )

    assert response.id == 55
    assert response.status == OrderStatus.NEGOTIATION
    assert captured_kwargs["lead_source"] == LeadSource.SITE
    assert captured_kwargs["initial_status"] == OrderStatus.NEGOTIATION
    assert captured_kwargs["customer_address"] == "г. Минск, ул. Тестовая 10"
    assert captured_kwargs["items"][0]["product_id"] == 7
    assert captured_kwargs["items"][0]["with_installation"] is True
    product_link_command = captured_kwargs["product_link_command"]
    assert isinstance(product_link_command, OrderProductLinkCommand)
    assert dict(product_link_command.unit_prices or {}) == {7: 3000}
    assert product_link_command.snapshots[7].title == "Checkout title"
    assert product_link_command.snapshots[7].currency == "BYN"
    assert captured_kwargs["commit"] is False
    assert captured_kwargs["order_technical_meta"]["public_catalog_pricing"] == {
        "snapshot_version": 1,
        "items": [
            {
                "product_id": 7,
                "title_snapshot": "Checkout title",
                "unit_price": 3000,
                "currency_snapshot": "BYN",
                "source": "shared_product",
            }
        ],
    }
    assert captured_kwargs["tenant_scope"] == tenant_scope
    assert captured_kwargs["commit"] is False
    assert captured_event["session"] is session
    assert captured_event["request"] is payload
    assert captured_event["tenant_scope"] == tenant_scope
    assert len(captured_event["request_key_hash"]) == 64
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_website_checkout_replay_does_not_repeat_mutation_or_enqueue(
    monkeypatch,
    tenant_scope,
):
    created_at = datetime.now()

    async def replay(*_args, **_kwargs):
        return SimpleNamespace(
            value=SimpleNamespace(
                id=56,
                status=OrderStatus.NEGOTIATION,
                total_amount=100,
                created_at=created_at,
            ),
            replayed=True,
        )

    async def must_not_enqueue(*_args, **_kwargs):
        raise AssertionError("replay repeated the transactional event enqueue")

    monkeypatch.setattr(PublicWriteIdempotencyService, "execute", replay)
    monkeypatch.setattr(
        TenantWebsiteEventService,
        "enqueue_checkout",
        must_not_enqueue,
    )

    payload = OrderPayload.model_validate(
        {
            "customer": {
                "name": "Тестовый клиент",
                "phone": "+375291112233",
                "email": "checkout@example.com",
            },
            "items": [{"product_id": 7, "quantity": 1}],
        }
    )

    response = await WebsiteOrderService.create_order(
        object(),
        payload,
        tenant_scope=tenant_scope,
        idempotency_key="checkout-request-unit-0002",
    )

    assert response.id == 56


@pytest.mark.asyncio
async def test_unoffered_checkout_fails_before_order_mutation(
    monkeypatch, tenant_scope
):
    mutation_calls = 0
    pricing_calls = 0

    async def fake_price_items(_session, items):
        nonlocal pricing_calls
        pricing_calls += 1
        raise AssertionError("hidden product must fail before installation pricing")

    async def fake_checkout_snapshots(_session, *, tenant_scope, product_ids):
        assert product_ids == {7}
        return {}

    async def fail_create_from_website(**_kwargs):
        nonlocal mutation_calls
        mutation_calls += 1
        raise AssertionError("hidden product must fail before order mutation")

    monkeypatch.setattr(
        InstallationPricingService,
        "price_public_items",
        fake_price_items,
    )
    monkeypatch.setattr(
        PublicCatalogVisibilityService,
        "get_checkout_snapshots",
        fake_checkout_snapshots,
    )
    monkeypatch.setattr(
        OrderService,
        "create_from_website",
        fail_create_from_website,
    )

    payload = OrderPayload.model_validate(
        {
            "customer": {
                "name": "Тестовый клиент",
                "phone": "+375291112233",
            },
            "items": [{"product_id": 7, "quantity": 1}],
        }
    )

    with pytest.raises(InstallationPricingError) as exc_info:
        await WebsiteOrderService._create_order_mutation(
            object(),
            payload,
            tenant_scope=tenant_scope,
            request_key_hash="0" * 64,
        )

    assert exc_info.value.code == "product_not_available"
    assert pricing_calls == 0
    assert mutation_calls == 0
