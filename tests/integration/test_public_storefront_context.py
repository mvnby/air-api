import json
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
_KEY_ID = "test-mvn-web"
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
    body: bytes = b"",
    signature: str | None = None,
) -> dict[str, str]:
    timestamp = int(time.time())
    return {
        "Host": "test",
        "X-MVN-Storefront-Key-Id": _KEY_ID,
        "X-MVN-Storefront-Host": "orsha.internal.mvn.by",
        "X-MVN-Storefront-Timestamp": str(timestamp),
        "X-MVN-Storefront-Signature": signature
        or StorefrontContextSignatureService.sign(
            secret=_SECRET,
            timestamp=timestamp,
            method=method,
            path_and_query=path,
            api_hostname="test",
            storefront_hostname="orsha.internal.mvn.by",
            body_sha256=StorefrontContextSignatureService.body_sha256(body),
        ),
    }


def _payload() -> dict[str, str]:
    return {
        "name": "Пилот Орша",
        "phone": "+375 (29) 111-22-33",
        "address": "Орша",
        "message": "Проверка второй витрины",
    }


def _json_body(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _configure_signing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_KEY_ID", _KEY_ID)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)
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
async def test_signed_context_routes_public_lead_to_secondary_storefront(
    async_client,
    db,
    monkeypatch,
):
    storefront = await _seed_secondary_storefront(db)
    _configure_signing(monkeypatch)
    payload = _payload()
    body = _json_body(payload)

    response = await async_client.post(
        _PATH,
        content=body,
        headers={**_headers(body=body), "Content-Type": "application/json"},
    )

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
    _configure_signing(monkeypatch)

    payload = {
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
    }
    body = _json_body(payload)

    response = await async_client.post(
        "/api/v1/orders",
        content=body,
        headers={
            **_headers(path="/api/v1/orders", body=body),
            "Content-Type": "application/json",
        },
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
    _configure_signing(monkeypatch)
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
async def test_signed_context_authenticates_public_catalog_raw_query(
    async_client,
    db,
    monkeypatch,
):
    await _seed_secondary_storefront(db)
    db.add(
        Product(
            title="Signed catalog product",
            slug="signed-catalog-product",
            price=1800,
            is_published=True,
        )
    )
    await db.commit()
    _configure_signing(monkeypatch)
    target = "/api/v1/products?limit=1"

    response = await async_client.get(
        target,
        headers=_headers(path=target, method="GET"),
    )

    assert response.status_code == 200
    assert response.json()["items"]
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_unsigned_non_api_host_is_rejected_without_creating_lead(
    async_client,
    db,
):
    await _seed_secondary_storefront(db)

    response = await async_client.post(
        _PATH,
        json=_payload(),
        headers={"Host": "orsha.internal.mvn.by"},
    )

    assert response.status_code == 401
    leads = (await db.execute(select(Lead))).scalars().all()
    assert leads == []


@pytest.mark.asyncio
async def test_unsigned_browser_origin_headers_cannot_switch_canonical_scope(
    async_client,
    db,
):
    await _seed_secondary_storefront(db)

    response = await async_client.post(
        _PATH,
        json=_payload(),
        headers={
            "Host": "test",
            "Origin": "https://orsha.internal.mvn.by",
            "X-Forwarded-Host": "orsha.internal.mvn.by",
        },
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
    _configure_signing(monkeypatch)

    body = _json_body(_payload())

    partial = await async_client.post(
        _PATH,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-MVN-Storefront-Host": "orsha.internal.mvn.by",
        },
    )
    wrong_path = await async_client.post(
        _PATH,
        content=body,
        headers={
            **_headers(path="/api/v1/orders", body=body),
            "Content-Type": "application/json",
        },
    )

    assert partial.status_code == 401
    assert wrong_path.status_code == 401
    leads = (await db.execute(select(Lead))).scalars().all()
    assert leads == []


@pytest.mark.asyncio
async def test_signed_context_rejects_body_tamper_without_creating_lead(
    async_client,
    db,
    monkeypatch,
):
    await _seed_secondary_storefront(db)
    _configure_signing(monkeypatch)
    signed_body = _json_body(_payload())
    tampered_body = _json_body({**_payload(), "message": "Подменённый текст"})

    response = await async_client.post(
        _PATH,
        content=tampered_body,
        headers={
            **_headers(body=signed_body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 401
    leads = (await db.execute(select(Lead))).scalars().all()
    assert leads == []


@pytest.mark.asyncio
async def test_context_selection_is_disabled_without_server_secret(
    async_client,
    db,
    monkeypatch,
):
    await _seed_secondary_storefront(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_KEY_ID", "")
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", "")
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID",
        _KEY_ID,
    )
    monkeypatch.setattr(
        settings,
        "STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET",
        _SECRET,
    )
    body = _json_body(_payload())

    response = await async_client.post(
        _PATH,
        content=body,
        headers={**_headers(body=body), "Content-Type": "application/json"},
    )

    assert response.status_code == 401
    leads = (await db.execute(select(Lead))).scalars().all()
    assert leads == []
