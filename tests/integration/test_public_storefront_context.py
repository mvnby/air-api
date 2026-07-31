import time

import pytest
from sqlmodel import select

from core.config import settings
from models import Lead, Order, Product
from models.tenancy import Storefront, StorefrontDomain
from services.storefront_context_signature_service import (
    StorefrontContextSignatureService,
)


_PATH = "/api/v1/leads/contact"
_SECRET = "test-storefront-secret-at-least-32-bytes"


async def _seed_secondary_storefront(db) -> Storefront:
    storefront = Storefront(
        id=2,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Орша",
        status="active",
        city="Орша",
        is_default=False,
    )
    db.add(storefront)
    await db.flush()
    db.add(
        StorefrontDomain(
            storefront_id=int(storefront.id),
            hostname="orsha.internal.mvn.by",
            status="active",
            is_primary=True,
        )
    )
    await db.commit()
    return storefront


def _headers(
    *,
    path: str = _PATH,
    method: str = "POST",
    signature: str | None = None,
) -> dict[str, str]:
    timestamp = int(time.time())
    return {
        "X-MVN-Storefront-Host": "orsha.internal.mvn.by",
        "X-MVN-Storefront-Timestamp": str(timestamp),
        "X-MVN-Storefront-Signature": signature
        or StorefrontContextSignatureService.sign(
            secret=_SECRET,
            timestamp=timestamp,
            method=method,
            path=path,
            hostname="orsha.internal.mvn.by",
        ),
    }


def _payload() -> dict[str, str]:
    return {
        "name": "Пилот Орша",
        "phone": "+375 (29) 111-22-33",
        "address": "Орша",
        "message": "Проверка второй витрины",
    }


@pytest.mark.asyncio
async def test_signed_context_routes_public_lead_to_secondary_storefront(
    async_client,
    db,
    monkeypatch,
):
    storefront = await _seed_secondary_storefront(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)

    response = await async_client.post(_PATH, json=_payload(), headers=_headers())

    assert response.status_code == 200
    lead = await db.get(Lead, response.json()["lead_id"])
    assert lead is not None
    assert (lead.tenant_id, lead.storefront_id) == (1, storefront.id)


@pytest.mark.asyncio
async def test_signed_context_routes_public_order_to_secondary_storefront(
    async_client,
    db,
    monkeypatch,
):
    storefront = await _seed_secondary_storefront(db)
    product = Product(
        title="Storefront context product",
        slug="storefront-context-product",
        price=2100,
        is_published=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)

    response = await async_client.post(
        "/api/v1/orders",
        json={
            "customer": {
                "name": "Покупатель Орша",
                "phone": "+375291112234",
                "email": "orsha@example.test",
                "address": "Орша",
                "type": "individual",
            },
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "with_installation": False,
                    "installation_options": [],
                }
            ],
            "comment": "Проверка provenance заказа",
        },
        headers=_headers(path="/api/v1/orders"),
    )

    assert response.status_code == 200
    order = await db.get(Order, response.json()["id"])
    assert order is not None
    assert (order.tenant_id, order.storefront_id) == (1, storefront.id)


@pytest.mark.asyncio
async def test_signed_context_exposes_public_storefront_dto_without_ids(
    async_client,
    db,
    monkeypatch,
):
    await _seed_secondary_storefront(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)
    path = "/api/v1/storefront/context"

    response = await async_client.get(
        path,
        headers=_headers(path=path, method="GET"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_slug": "mvn",
        "tenant_kind": "operator",
        "storefront_slug": "orsha",
        "display_name": "MVN Орша",
        "hostname": "orsha.internal.mvn.by",
        "city": "Орша",
        "default_locale": "ru-BY",
        "currency": "BYN",
    }
    assert "tenant_id" not in response.json()
    assert "storefront_id" not in response.json()
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["cdn-cache-control"] == "no-store"
    assert response.headers["vary"] == "X-MVN-Storefront-Host"


@pytest.mark.asyncio
async def test_unsigned_host_header_cannot_select_secondary_storefront(
    async_client,
    db,
):
    await _seed_secondary_storefront(db)

    response = await async_client.post(
        _PATH,
        json=_payload(),
        headers={"Host": "orsha.internal.mvn.by"},
    )

    assert response.status_code == 200
    lead = await db.get(Lead, response.json()["lead_id"])
    assert lead is not None
    assert (lead.tenant_id, lead.storefront_id) == (1, 1)


@pytest.mark.asyncio
async def test_unsigned_context_endpoint_keeps_canonical_mvn_projection(
    async_client,
    db,
):
    db.add(
        StorefrontDomain(
            storefront_id=1,
            hostname="mvn.by",
            status="active",
            is_primary=True,
        )
    )
    await db.commit()

    response = await async_client.get("/api/v1/storefront/context")

    assert response.status_code == 200
    assert response.json()["tenant_slug"] == "mvn"
    assert response.json()["storefront_slug"] == "main"
    assert response.json()["hostname"] == "mvn.by"


@pytest.mark.asyncio
async def test_partial_or_tampered_context_fails_closed(
    async_client,
    db,
    monkeypatch,
):
    await _seed_secondary_storefront(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)

    partial = await async_client.post(
        _PATH,
        json=_payload(),
        headers={"X-MVN-Storefront-Host": "orsha.internal.mvn.by"},
    )
    wrong_path = await async_client.post(
        _PATH,
        json=_payload(),
        headers=_headers(path="/api/v1/orders"),
    )

    assert partial.status_code == 401
    assert wrong_path.status_code == 401
    leads = (await db.execute(select(Lead))).scalars().all()
    assert leads == []


@pytest.mark.asyncio
async def test_context_selection_is_disabled_without_server_secret(
    async_client,
    db,
    monkeypatch,
):
    await _seed_secondary_storefront(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", "")
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET",
        _SECRET,
    )

    response = await async_client.post(_PATH, json=_payload(), headers=_headers())

    assert response.status_code == 401
    leads = (await db.execute(select(Lead))).scalars().all()
    assert leads == []
