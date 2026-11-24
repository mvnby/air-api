from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from sqlalchemy import func
from sqlmodel import select

from core.config import settings
from models import Order, OrderStatus, Product
from models.personal_offer import PersonalOffer, PersonalOfferPublication
from models.tenancy import Storefront, StorefrontDomain
from services import personal_offer_service
from services.manager_storefront_selector_service import MANAGER_STOREFRONT_HEADER
from services.storefront_context_signature_service import StorefrontContextSignatureService


_MANAGER_PATH = "/api/manager/personal-offers"
_HOSTS = ("mvn.by", "www.mvn.by", "other.mvn.by")
_KEY_ID = "personal-offer-test"
_SIGNING_SECRET = "test-storefront-secret-at-least-32-bytes"


async def _manager_headers(client):
    response = await client.post("/login/access-token", data={
        "username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD,
    })
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seed_domains(db, monkeypatch):
    secondary = Storefront(tenant_id=1, slug="other", display_name="Other MVN", status="active")
    db.add(secondary)
    await db.flush()
    db.add_all([
        StorefrontDomain(
            storefront_id=storefront_id, hostname=hostname, status="active",
            is_primary=is_primary, verified_at=datetime.now(timezone.utc),
        )
        for storefront_id, hostname, is_primary in (
            (1, _HOSTS[0], True), (1, _HOSTS[1], False), (secondary.id, _HOSTS[2], True)
        )
    ])
    await db.commit()
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON", json.dumps({
        "keys": {
            f"{_KEY_ID}-{index}": {
                "secret": f"{_SIGNING_SECRET}-{index}", "host_roles": {host: "primary"},
            }
            for index, host in enumerate(_HOSTS)
        },
    }))
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_KEY_ID", "")
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", "")
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS", False)
    return secondary


def _signed_read(path, hostname):
    timestamp = int(datetime.now(timezone.utc).timestamp())
    index = _HOSTS.index(hostname)
    signature = StorefrontContextSignatureService.sign(
        secret=f"{_SIGNING_SECRET}-{index}", timestamp=timestamp, method="GET",
        path_and_query=path, api_hostname="test", storefront_hostname=hostname,
        body_sha256=StorefrontContextSignatureService.body_sha256(b""), idempotency_key_sha256="",
    )
    return {
        "X-MVN-Storefront-Key-Id": f"{_KEY_ID}-{index}", "X-MVN-Storefront-Host": hostname,
        "X-MVN-Storefront-Timestamp": str(timestamp), "X-MVN-Storefront-Signature": signature,
    }


def _offer_path(record):
    return "/api/v1/personal-offers/" + record["published"]["url"].rstrip("/").rsplit("/", 1)[-1]


def _draft(product_id, order_id=None):
    return {
        "order_id": order_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "rooms": [
            {
                "title": "  Зал  ",
                "installation": {"mode": "fixed", "price_byn": "500.25", "description": "Трасса до 3 м"},
                "options": [{"product_id": product_id, "price_byn": "1520.10", "note": "Оптимальный"}],
            }, {
                "title": " ",
                "installation": {"mode": "unknown"},
                "options": [{"product_id": product_id, "price_byn": "1520.10"}],
            }, {
                "title": "Баня",
                "installation": {"mode": "none", "description": "Скрытый комментарий"},
                "options": [{"product_id": product_id, "price_byn": "1520.10"}],
            },
        ],
    }


async def test_personal_offer_publication_lifecycle(async_client, db, monkeypatch):
    await _seed_domains(db, monkeypatch)
    product = Product(
        title="Test split", slug="test-split", product_kind="complete_split_system",
        price=1570, is_published=True, main_image="/media/products/test.webp", power_cooling=3.5,
        specs={"noise_indoor": "23/27/32 дБ", "wifi_builtin": True, "inverter": True},
    )
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION, comment="Внутренняя заявка")
    db.add_all([product, order])
    await db.commit()

    draft_payload = _draft(product.id, order.id)
    assert (await async_client.post(_MANAGER_PATH, json=draft_payload)).status_code == 401
    headers = await _manager_headers(async_client)
    created = await async_client.post(_MANAGER_PATH, json=draft_payload, headers=headers)
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["order_id"] == order.id
    assert draft["published"] is None
    manager_path = f"{_MANAGER_PATH}/{draft['id']}"
    preview = await async_client.post(f"{manager_path}/preview", headers=headers)
    assert preview.status_code == 200, preview.text
    projected = preview.json()
    assert list(projected) == ["expires_at", "rooms"]
    assert [room["title"] for room in projected["rooms"]] == ["Зал", "Помещение 2", "Баня"]
    options = [room["options"][0] for room in projected["rooms"]]
    assert set(options[0]) == {
        "title", "slug", "main_image", "price_byn", "original_price_byn", "total_price_byn", "note",
        "cooling_power_kw", "noise_indoor_min_db", "is_inverter", "wifi",
    }
    assert options[0]["price_byn"] == "1520.10"
    assert options[0]["original_price_byn"] == "1570"
    assert options[0]["noise_indoor_min_db"] == 23
    assert options[0]["is_inverter"] is True
    assert options[0]["wifi"] == "builtin"
    assert [option["total_price_byn"] for option in options] == ["2020.35", None, None]
    assert projected["rooms"][2]["installation"]["description"] is None

    first_command = {"request_id": str(uuid4()), "expected_version": draft["version"]}
    published = await async_client.post(f"{manager_path}/publish", headers=headers, json=first_command)
    assert published.status_code == 200, published.text
    first = published.json()
    assert published.headers["cache-control"] == "private, no-store"
    assert first["published"]["url"].startswith("https://mvn.by/predlozhenie/")
    public_path = _offer_path(first)
    assert len(public_path.rsplit("/", 1)[-1]) == 43

    replay = await async_client.post(f"{manager_path}/publish", headers=headers, json=first_command)
    assert replay.json() == first
    assert (await db.execute(select(func.count(PersonalOfferPublication.id)))).scalar_one() == 1
    listed = await async_client.get(f"{_MANAGER_PATH}?order_id={order.id}", headers=headers)
    assert listed.json() == {"items": [first], "has_more": False}
    assert (await async_client.get(public_path)).status_code == 401

    public_headers = _signed_read(public_path, _HOSTS[0])
    public = await async_client.get(public_path, headers=public_headers)
    assert public.status_code == 200, public.text
    assert public.headers["cache-control"] == "private, no-store"
    assert public.headers["x-robots-tag"] == "noindex, nofollow"
    assert public.json() == projected

    for other_host in _HOSTS[1:]:
        other = await async_client.get(public_path, headers=_signed_read(public_path, other_host))
        assert other.status_code == 404, other.text
        assert other.json() == {"detail": "Offer unavailable"}

    product.price = 1650
    await db.commit()
    draft_payload["rooms"] = [{
        "selection_mode": "package",
        "show_total": True,
        "installation": {"mode": "fixed", "price_byn": "500.25"},
        "options": [
            {"product_id": product.id, "price_byn": "1520.10", "note": "Гостиная"},
            {"product_id": product.id, "price_byn": "1520.20", "note": "Спальня"},
        ],
    }]
    edited = await async_client.put(
        manager_path, headers=headers, json={**draft_payload, "expected_version": first["version"]},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["published"] == first["published"]
    stale_manager = await async_client.put(
        manager_path, headers=headers, json={**_draft(product.id, order.id), "expected_version": edited.json()["version"]},
    )
    assert stale_manager.status_code == 409, stale_manager.text
    assert (await async_client.get(public_path, headers=public_headers)).json() == projected
    new_preview = await async_client.post(f"{manager_path}/preview", headers=headers)
    package = new_preview.json()["rooms"][0]
    assert package["title"] == "Комплект оборудования"
    assert package["selection_mode"] == "package"
    assert package["equipment_total_byn"] == "3040.30"
    assert package["total_with_installation_byn"] == "3540.55"
    assert all(option["total_price_byn"] is None for option in package["options"])
    assert package["options"][0]["original_price_byn"] == "1650"

    second_command = {"request_id": str(uuid4()), "expected_version": edited.json()["version"]}
    second = await async_client.post(f"{manager_path}/publish", headers=headers, json=second_command)
    assert second.status_code == 200, second.text
    new_path = _offer_path(second.json())
    new_headers = _signed_read(new_path, _HOSTS[0])
    assert new_path != public_path
    assert (await async_client.get(public_path, headers=public_headers)).status_code == 404
    assert (await async_client.get(new_path, headers=new_headers)).json() == new_preview.json()

    def future():
        return datetime.now(timezone.utc) + timedelta(days=8)

    with monkeypatch.context() as patch:
        patch.setattr(personal_offer_service, "utc_now", future)
        assert (await async_client.get(new_path, headers=new_headers)).status_code == 404

    revoked = await async_client.post(
        f"{manager_path}/revoke", headers=headers, json={"expected_version": second.json()["version"]},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["published"] is None
    assert (await async_client.get(new_path, headers=new_headers)).status_code == 404
    assert await db.get(Order, order.id) is order
    assert order.status == OrderStatus.NEGOTIATION


async def test_personal_offer_draft_rejects_ineligible_products_and_foreign_order(async_client, db, monkeypatch):
    secondary = await _seed_domains(db, monkeypatch)
    product = Product(
        title="Hidden product", slug="hidden-product", product_kind="complete_split_system",
        price=1570, is_published=False,
    )
    order = Order(tenant_id=1, storefront_id=secondary.id, status=OrderStatus.NEGOTIATION)
    db.add_all([product, order])
    await db.commit()
    headers = await _manager_headers(async_client)
    wrong_order = await async_client.post(_MANAGER_PATH, json=_draft(product.id, order.id), headers=headers)
    assert wrong_order.status_code == 404
    absent_product = await async_client.post(_MANAGER_PATH, json=_draft(product.id), headers=headers)
    assert absent_product.status_code == 409
    assert (await async_client.get(_MANAGER_PATH, headers=headers)).json() == {"items": [], "has_more": False}


async def test_manager_renames_and_removes_a_published_offer_without_exposing_internal_title(
    async_client, db, monkeypatch,
):
    other_storefront = await _seed_domains(db, monkeypatch)
    product = Product(
        title="Test split", slug="offer-management-split", product_kind="complete_split_system",
        price=1570, is_published=True,
    )
    db.add(product)
    await db.commit()
    headers = await _manager_headers(async_client)
    draft = _draft(product.id)
    response = await async_client.post(_MANAGER_PATH, headers=headers, json={**draft, "title": "  Подбор для склада  "})
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["title"] == "Подбор для склада"
    offer_id = created["id"]
    manager_path = f"{_MANAGER_PATH}/{offer_id}"
    publish = await async_client.post(
        f"{manager_path}/publish", headers=headers,
        json={"request_id": str(uuid4()), "expected_version": created["version"]},
    )
    assert publish.status_code == 200, publish.text
    published_offer = publish.json()
    public_path = _offer_path(published_offer)
    public_headers = _signed_read(public_path, _HOSTS[0])
    before = await async_client.get(public_path, headers=public_headers)
    assert before.status_code == 200, before.text
    assert "Подбор для склада" not in before.text

    rename = {"title": "  Склад — инверторы  ", "expected_version": published_offer["version"]}
    other_scope = {**headers, MANAGER_STOREFRONT_HEADER: other_storefront.slug}
    assert (await async_client.patch(manager_path, headers=other_scope, json=rename)).status_code == 404
    result = await async_client.patch(manager_path, headers=headers, json=rename)
    assert result.status_code == 200, result.text
    renamed = result.json()
    assert renamed["title"] == "Склад — инверторы"
    assert renamed["version"] == published_offer["version"] + 1
    assert renamed["published"] == published_offer["published"]
    assert renamed["rooms"] == created["rooms"]
    assert (await async_client.get(public_path, headers=public_headers)).json() == before.json()
    assert (await async_client.patch(manager_path, headers=headers, json=rename)).status_code == 409

    # Existing Manager clients omit the new field on a draft update.
    edited = await async_client.put(
        manager_path, headers=headers, json={**draft, "expected_version": renamed["version"]},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == renamed["title"]
    delete = {"expected_version": edited.json()["version"]}
    assert (await async_client.delete(manager_path, headers=other_scope, params=delete)).status_code == 404
    assert (
        await async_client.delete(manager_path, headers=headers, params={"expected_version": renamed["version"]})
    ).status_code == 409
    assert (await async_client.get(public_path, headers=public_headers)).status_code == 200

    deleted = await async_client.delete(manager_path, headers=headers, params=delete)
    assert deleted.status_code == 204, deleted.text
    assert deleted.headers["cache-control"] == "private, no-store"
    assert (await async_client.get(_MANAGER_PATH, headers=headers)).json() == {"items": [], "has_more": False}
    assert (await async_client.get(manager_path, headers=headers)).status_code == 404
    assert (await async_client.post(f"{manager_path}/preview", headers=headers)).status_code == 404
    assert (await async_client.get(public_path, headers=public_headers)).status_code == 404
    assert (await async_client.delete(manager_path, headers=headers, params=delete)).status_code == 404

    stored = await db.get(PersonalOffer, offer_id)
    receipt = (await db.execute(
        select(PersonalOfferPublication).where(PersonalOfferPublication.offer_id == offer_id)
    )).scalar_one()
    assert stored.title == renamed["title"]
    assert stored.deleted_at is not None
    assert receipt.revoked_at == stored.deleted_at
