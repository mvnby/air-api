from __future__ import annotations

import asyncio
import json
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.config import settings
from models import (
    Customer,
    IntegrationOutboxEvent,
    Order,
    OrderProductLink,
    Product,
    PublicWriteIdempotency,
    Storefront,
    StorefrontDomain,
    Tenant,
    TenantOffer,
)
from schemas import OrderPayload
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
)
from services.public_write_idempotency_service import PublicWriteIdempotencyService
from services.storefront_context_signature_service import (
    StorefrontContextSignatureService,
)
from services.tenant_scope_service import TenantScope
from services.website_order_service import WebsiteOrderService


_KEY_ID = "test-public-catalog"
_SECRET = "test-public-catalog-secret-at-least-32-bytes"
_SECONDARY_HOST = "orsha.catalog.test"


def _signed_read_headers(path_and_query: str) -> dict[str, str]:
    timestamp = int(time.time())
    return {
        "Host": "test",
        "X-MVN-Storefront-Key-Id": _KEY_ID,
        "X-MVN-Storefront-Host": _SECONDARY_HOST,
        "X-MVN-Storefront-Timestamp": str(timestamp),
        "X-MVN-Storefront-Signature": StorefrontContextSignatureService.sign(
            secret=_SECRET,
            timestamp=timestamp,
            method="GET",
            path_and_query=path_and_query,
            api_hostname="test",
            storefront_hostname=_SECONDARY_HOST,
            body_sha256=StorefrontContextSignatureService.EMPTY_BODY_SHA256,
            idempotency_key_sha256="",
        ),
    }


def _configure_signing(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON",
        json.dumps(
            {
                "keys": {
                    _KEY_ID: {
                        "secret": _SECRET,
                        "host_roles": {_SECONDARY_HOST: "primary"},
                    }
                }
            }
        ),
    )
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_KEY_ID", "")
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", "")
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID",
        "",
    )
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET",
        "",
    )


@pytest.mark.asyncio
async def test_secondary_catalog_scopes_offers_before_sort_and_pagination(
    async_client,
    db,
    monkeypatch,
):
    storefront = Storefront(
        id=2,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Orsha",
        status="active",
        city="Orsha",
        is_default=False,
    )
    db.add(storefront)
    await db.flush()
    db.add(
        StorefrontDomain(
            storefront_id=int(storefront.id),
            hostname=_SECONDARY_HOST,
            status="active",
            is_primary=True,
        )
    )
    low_offer = Product(
        title="Offer low",
        slug="offer-low",
        price=9000,
        is_published=True,
    )
    high_offer = Product(
        title="Offer high",
        slug="offer-high",
        price=1000,
        is_published=True,
    )
    no_offer = Product(
        title="No offer",
        slug="no-offer",
        price=2000,
        is_published=True,
    )
    disabled_offer = Product(
        title="Disabled offer",
        slug="disabled-offer",
        price=2500,
        is_published=True,
    )
    db.add_all([low_offer, high_offer, no_offer, disabled_offer])
    await db.flush()
    db.add_all(
        [
            TenantOffer(
                tenant_id=1,
                storefront_id=2,
                product_id=int(low_offer.id),
                price=3000,
                old_price=3500,
                status="active",
                is_published=True,
                created_by_username="test",
                updated_by_username="test",
            ),
            TenantOffer(
                tenant_id=1,
                storefront_id=2,
                product_id=int(high_offer.id),
                price=7000,
                status="active",
                is_published=True,
                created_by_username="test",
                updated_by_username="test",
            ),
            TenantOffer(
                tenant_id=1,
                storefront_id=2,
                product_id=int(disabled_offer.id),
                price=4000,
                status="disabled",
                is_published=False,
                created_by_username="test",
                updated_by_username="test",
            ),
        ]
    )
    await db.commit()
    _configure_signing(monkeypatch)

    target = "/api/v1/products?sort=price_asc&limit=1&page=2"
    response = await async_client.get(
        target,
        headers=_signed_read_headers(target),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"] == {
        "total": 2,
        "page": 2,
        "limit": 1,
        "pages": 2,
    }
    assert [item["slug"] for item in payload["items"]] == [high_offer.slug]
    assert payload["items"][0]["price"] == 7000
    assert no_offer.slug not in {item["slug"] for item in payload["items"]}
    assert disabled_offer.slug not in {
        item["slug"] for item in payload["items"]
    }

    first_page_target = "/api/v1/products?sort=price_asc&limit=1"
    first_page = await async_client.get(
        first_page_target,
        headers=_signed_read_headers(first_page_target),
    )
    assert first_page.status_code == 200, first_page.text
    assert first_page.json()["items"][0]["slug"] == low_offer.slug
    assert first_page.json()["items"][0]["price"] == 3000
    assert first_page.json()["items"][0]["old_price"] == 3500


@pytest.mark.asyncio
async def test_concurrent_checkout_isolated_by_exact_tenant_storefront_scope(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as setup:
        tenant_b = Tenant(
            id=2,
            slug="tenant-b",
            display_name="Tenant B",
            status="active",
            is_system=False,
        )
        storefront_a = Storefront(
            id=2,
            tenant_id=1,
            slug="orsha",
            display_name="MVN Orsha",
            status="active",
            currency="BYN",
            is_default=False,
        )
        storefront_b = Storefront(
            id=3,
            tenant_id=2,
            slug="main",
            display_name="Tenant B Main",
            status="active",
            currency="EUR",
            is_default=True,
        )
        product = Product(
            title="Shared catalog product",
            slug="shared-catalog-product",
            price=9999,
            is_published=True,
        )
        setup.add(tenant_b)
        await setup.flush()
        setup.add_all([storefront_a, storefront_b, product])
        await setup.flush()
        setup.add_all(
            [
                TenantOffer(
                    tenant_id=1,
                    storefront_id=2,
                    product_id=int(product.id),
                    price=3100,
                    status="active",
                    is_published=True,
                    created_by_username="test",
                    updated_by_username="test",
                ),
                TenantOffer(
                    tenant_id=2,
                    storefront_id=3,
                    product_id=int(product.id),
                    price=4200,
                    status="active",
                    is_published=True,
                    created_by_username="test",
                    updated_by_username="test",
                ),
            ]
        )
        await setup.commit()
        product_id = int(product.id)

    payload = OrderPayload.model_validate(
        {
            "customer": {
                "name": "Same public customer",
                "phone": "+375291112233",
            },
            "items": [{"product_id": product_id, "quantity": 1}],
            "comment": "Same request content across isolated scopes",
        }
    )
    scopes = (
        TenantScope(
            tenant_id=1,
            storefront_id=2,
            is_system=True,
            is_canonical_storefront=False,
        ),
        TenantScope(
            tenant_id=2,
            storefront_id=3,
            is_system=False,
            is_canonical_storefront=False,
        ),
    )
    idempotency_key = "cross-scope-checkout-same-key-0001"
    barrier = asyncio.Barrier(2)

    async def submit(scope: TenantScope):
        async with factory() as session:
            await barrier.wait()
            return await WebsiteOrderService.create_order(
                session,
                payload,
                tenant_scope=scope,
                idempotency_key=idempotency_key,
            )

    response_a, response_b = await asyncio.gather(
        submit(scopes[0]),
        submit(scopes[1]),
    )
    assert response_a.id != response_b.id

    expected = {
        (1, 2): (3100, "BYN"),
        (2, 3): (4200, "EUR"),
    }
    async with factory() as verification:
        orders = list(
            (
                await verification.execute(
                    select(Order).where(
                        Order.id.in_([response_a.id, response_b.id])
                    )
                )
            ).scalars()
        )
        links = list(
            (
                await verification.execute(
                    select(OrderProductLink).where(
                        OrderProductLink.order_id.in_(
                            [response_a.id, response_b.id]
                        )
                    )
                )
            ).scalars()
        )
        customers = list(
            (
                await verification.execute(
                    select(Customer).where(
                        Customer.id.in_([order.customer_id for order in orders])
                    )
                )
            ).scalars()
        )
        receipts = list(
            (
                await verification.execute(
                    select(PublicWriteIdempotency).where(
                        PublicWriteIdempotency.key_hash
                        == PublicWriteIdempotencyService.key_hash(
                            idempotency_key
                        )
                    )
                )
            ).scalars()
        )
        events = list(
            (
                await verification.execute(
                    select(IntegrationOutboxEvent).where(
                        IntegrationOutboxEvent.event_type
                        == TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
                        IntegrationOutboxEvent.aggregate_id.in_(
                            [str(response_a.id), str(response_b.id)]
                        ),
                    )
                )
            ).scalars()
        )

    assert len(orders) == len(links) == len(customers) == len(receipts) == 2
    assert len(events) == 2
    assert {(order.tenant_id, order.storefront_id) for order in orders} == set(
        expected
    )
    assert {customer.tenant_id for customer in customers} == {1, 2}
    assert {receipt.tenant_id for receipt in receipts} == {1, 2}
    assert {
        (receipt.tenant_id, receipt.storefront_id) for receipt in receipts
    } == set(expected)

    orders_by_id = {int(order.id): order for order in orders}
    for link in links:
        order = orders_by_id[int(link.order_id)]
        price, currency = expected[(order.tenant_id, order.storefront_id)]
        assert link.product_id == product_id
        assert link.price == price
        assert link.title_snapshot == "Shared catalog product"
        assert link.currency_snapshot == currency
        pricing = order.technical_meta["public_catalog_pricing"]
        assert pricing["snapshot_version"] == 1
        assert pricing["items"] == [
            {
                "product_id": product_id,
                "title_snapshot": "Shared catalog product",
                "unit_price": price,
                "currency_snapshot": currency,
                "source": "tenant_offer",
            }
        ]

    for event in events:
        tenant_id = int(event.payload["tenant_id"])
        storefront_id = int(event.payload["storefront_id"])
        price, currency = expected[(tenant_id, storefront_id)]
        assert event.payload["currency"] == currency
        assert event.payload["product_lines"][0]["unit_price"] == str(price)
