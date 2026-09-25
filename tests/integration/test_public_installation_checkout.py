"""PostgreSQL contract for create-only public installation acceptance."""

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import func, select

from models import (
    InstallationEstimateRevision, InstallationPriceBook, InstallationPreviewSnapshot,
    IntegrationOutboxEvent,
    Order, OrderServiceLink, Product, PublicInstallationPreviewClaim, Tenant,
)
from models.tenancy import TenantScope
from schemas_installation_price_book import InstallationPreviewPayload
from schemas_public_checkout import OrderPayload
from services.installation_price_book_service import InstallationPriceBookService as Book
from services.public_installation_checkout_service import PublicInstallationCheckoutService
from services.public_write_idempotency_service import PublicWriteIdempotencyUnavailable
from services.website_order_service import WebsiteOrderService


def _entry(*, base="500.00"):
    def rule(number, code, kind, price, optional=False):
        return {"id": number, "code": code, "rule_type": kind, "name": code,
                "line_template": "{name}", "unit": "м" if kind == "per_meter_over_included" else "шт",
                "unit_price": price, "is_optional": optional, "sort_order": number}

    return {"tariff_id": 1, "code": "installation.wall.2_4", "mode": "fixed",
            "match": {"product_kind": "complete_split_system", "indoor_type": "wall",
                      "capacity_min_kw": "2", "capacity_max_kw": "4",
                      "pipe_liquid": '1/4"', "pipe_gas": '3/8"'},
            "base_price": base, "short_name": "Монтаж", "description": "Монтаж",
            "included_route_m": "3", "included_holes": {"diamond": "1"},
            "rules": [
                rule(1, "route.extra_m", "per_meter_over_included", "10.25"),
                rule(2, "hole.diamond.extra", "per_hole_manual", "50.00"),
                rule(3, "pump.supply", "per_unit_manual", "80.00", True),
                rule(4, "pump.install", "per_unit_manual", "20.00", True),
                rule(5, "access.lift", "fixed_once", "100.00", True),
                rule(6, "discount.equipment_bundle", "fixed_once", "0.01"),
            ]}


async def _seed(session: AsyncSession):
    product = Product(title="Wall AC", slug="public-install-wall-ac", price=2000,
                      product_kind="complete_split_system", is_published=True,
                      specs={"type": "wall", "indoor_type": "wall", "capacity_cooling_kw": "2.5",
                             "pipe_liquid": '1/4"', "pipe_gas": '3/8"'})
    session.add(product)
    session.add(InstallationPriceBook(tenant_id=1, revision=1,
                                      fingerprint="public-checkout-book-one", entries=[_entry()]))
    await session.commit()
    return int(product.id)


async def _preview(session: AsyncSession, product_id: int, *, key: str,
                   with_pump: bool = False, count: int = 1):
    installations = [{"key": "ac-one", "display_label": "№1", "product_id": product_id,
                      "route_length_m": "6", "holes_by_type": {"diamond": 2},
                      "extras": ([{"code": "pump.supply"}, {"code": "pump.install"}]
                                 if with_pump else [{"code": "pump.install"}])}]
    for index in range(2, count + 1):
        installations.append({"key": f"ac-{index}", "display_label": f"№{index}",
                              "product_id": product_id, "route_length_m": "3",
                              "holes_by_type": {"diamond": 1}})
    return await Book.preview(
        session, TenantScope(tenant_id=1, storefront_id=1, is_system=True,
                             is_canonical_storefront=True),
        InstallationPreviewPayload.model_validate({
            "installations": installations, "site_extras": [{"code": "access.lift"}],
        }), idempotency_key=key,
    )


def _order_payload(product_id: int, preview, *, quantity: int = 1,
                   extra_product: int | None = None) -> dict:
    items = [{"product_id": product_id, "quantity": quantity}]
    lines = [{"product_id": product_id, "quantity": quantity,
              "unit_price": "2000.00", "currency": "BYN"}]
    total = Decimal("2000.00") * quantity + preview.total
    if extra_product is not None:
        items.append({"product_id": extra_product, "quantity": 1})
        lines.append({"product_id": extra_product, "quantity": 1,
                      "unit_price": "100.00", "currency": "BYN"})
        total += Decimal("100.00")
    return {"customer": {"name": "Public Buyer", "phone": "+375291112233"},
            "items": items,
            "installation_acceptance": {
                "preview_ref": preview.preview_ref,
                "expected_product_lines": lines,
                "expected_order_total": str(total),
            }}


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 20])
async def test_public_checkout_attaches_exact_preview_and_bounded_event(async_client, db, count):
    product_id = await _seed(db)
    preview = await _preview(db, product_id, key=f"public-{count}-ac-preview",
                             with_pump=True, count=count)
    assert preview.status == "fixed"
    if count == 2:
        assert preview.total == Decimal("1280.73")
    assert [part.code for part in preview.components].count("access.lift") == 1
    body = _order_payload(product_id, preview, quantity=count)
    response = await async_client.post("/api/v1/orders", json=body,
                                       headers={"Idempotency-Key": f"public-{count}-ac-checkout"})
    assert response.status_code == 200, response.text
    order_id = response.json()["id"]
    order = await db.get(Order, order_id)
    await db.refresh(order, attribute_names=["proposals", "product_links", "service_links"])
    selected = next(proposal for proposal in order.proposals if proposal.is_selected)
    attached = [line for line in order.service_links if line.proposal_id == selected.id]
    assert len(attached) == 1
    assert attached[0].installation_estimate_revision_id is not None
    assert Decimal(str(attached[0].price)) == preview.total
    assert len(attached[0].title) > 180
    assert "вышка" in attached[0].title.lower()
    assert "поставка насоса" in attached[0].title.lower()
    assert order.product_links[0].is_installation_included is False
    assert order.product_links[0].installation_price == 0
    assert Decimal(str(order.total_amount)) == Decimal("2000.00") * count + preview.total
    revision = await db.get(InstallationEstimateRevision, attached[0].installation_estimate_revision_id)
    assert Decimal(str(revision.total)) == preview.total
    assert revision.snapshot["confirmation"]["actor"] == "public_checkout"
    event = (await db.execute(select(IntegrationOutboxEvent).where(
        IntegrationOutboxEvent.aggregate_type == "order",
        IntegrationOutboxEvent.aggregate_id == str(order_id),
    ))).scalars().one()
    event_line = event.payload["service_lines"][0]
    assert len(event_line["title"]) <= 180
    assert str(count) in event_line["title"]
    assert str(order_id) in event_line["title"]
    assert Decimal(event_line["unit_price"]) == preview.total
    assert event_line["title"] != attached[0].title
    repeated = await async_client.post("/api/v1/orders", json=body,
                                       headers={"Idempotency-Key": f"public-{count}-ac-checkout"})
    assert repeated.json() == response.json()
    changed_body = {**body, "comment": "different buyer intent"}
    changed_key = await async_client.post("/api/v1/orders", json=changed_body,
                                          headers={"Idempotency-Key": f"public-{count}-ac-checkout"})
    assert changed_key.status_code == 409
    assert await db.scalar(select(func.count(Order.id))) == 1
    refused = await async_client.post("/api/v1/orders", json=body,
                                      headers={"Idempotency-Key": f"public-{count}-ac-other-key"})
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "preview_already_used"
    assert await db.scalar(select(func.count(PublicInstallationPreviewClaim.id))) == 1


@pytest.mark.asyncio
async def test_public_acceptance_does_not_activate_partner_checkout(db):
    product_id = await _seed(db)
    preview = await _preview(db, product_id, key="partner-read-only-preview")
    payload = OrderPayload.model_validate(_order_payload(product_id, preview))
    partner = TenantScope(tenant_id=1, storefront_id=1, is_canonical_storefront=False)
    with pytest.raises(HTTPException) as denied:
        await WebsiteOrderService.create_order(
            db, payload, tenant_scope=partner, idempotency_key="partner-no-checkout-key",
        )
    assert denied.value.status_code == 404
    assert await db.scalar(select(func.count(Order.id))) == 0


@pytest.mark.asyncio
async def test_public_checkout_rejects_pump_supply_with_unmatched_accessory_and_expired_ref(async_client, db):
    product_id = await _seed(db)
    accessory = Product(title="Accessory", slug="public-install-accessory", price=100,
                        product_kind="accessory", is_published=True)
    db.add(accessory)
    await db.commit()
    preview = await _preview(db, product_id, key="public-pump-ambiguous", with_pump=True)
    body = _order_payload(product_id, preview, extra_product=int(accessory.id))
    refused = await async_client.post("/api/v1/orders", json=body,
                                      headers={"Idempotency-Key": "public-pump-ambiguous-submit"})
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "pump_supply_cart_ambiguous"
    assert await db.scalar(select(func.count(Order.id))) == 0
    saved = (await db.execute(select(InstallationPreviewSnapshot).where(
        InstallationPreviewSnapshot.token_hash == hashlib.sha256(
            preview.preview_ref.encode()).hexdigest(),
    ))).scalars().one()
    saved.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.add(saved)
    await db.commit()
    expired = await async_client.post("/api/v1/orders", json=_order_payload(product_id, preview),
                                      headers={"Idempotency-Key": "public-expired-submit"})
    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "preview_expired"
    assert await db.scalar(select(func.count(Order.id))) == 0


@pytest.mark.asyncio
async def test_distinct_public_checkout_keys_and_concurrent_publication_serialize(db_engine, monkeypatch):
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True,
                        is_canonical_storefront=True)
    async with factory() as setup:
        product_id = await _seed(setup)
        preview = await _preview(setup, product_id, key="public-race-preview")
    payload = OrderPayload.model_validate(_order_payload(product_id, preview))

    async def checkout(key, submission=payload):
        async with factory() as session:
            return await WebsiteOrderService.create_order(
                session, submission, tenant_scope=scope, idempotency_key=key,
            )

    outcomes = await asyncio.wait_for(asyncio.gather(
        checkout("public-race-first"), checkout("public-race-second"),
        return_exceptions=True,
    ), timeout=15)
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    loser = next(item for item in outcomes if isinstance(item, Exception))
    if isinstance(loser, PublicWriteIdempotencyUnavailable):
        with pytest.raises(HTTPException) as retried:
            await checkout("public-race-second" if not isinstance(outcomes[0], Exception)
                           else "public-race-first")
        loser = retried.value
    assert isinstance(loser, HTTPException) and loser.detail.get("code") == "preview_already_used"
    async with factory() as verify:
        assert await verify.scalar(select(func.count(Order.id))) == 1
        assert await verify.scalar(select(func.count(OrderServiceLink.id))) == 1

    async with factory() as setup:
        new_preview = await _preview(setup, product_id, key="public-publish-race-preview")
    new_payload = OrderPayload.model_validate(_order_payload(product_id, new_preview))
    entered = asyncio.Event()
    release = asyncio.Event()
    original = PublicInstallationCheckoutService.create

    async def pause_after_receipt(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(PublicInstallationCheckoutService, "create", pause_after_receipt)
    async with factory() as publication:
        await publication.execute(select(Tenant).where(Tenant.id == 1).with_for_update(key_share=True))
        pending = asyncio.create_task(checkout("public-race-after-publish", new_payload))
        await asyncio.wait_for(entered.wait(), timeout=5)
        publication.add(InstallationPriceBook(tenant_id=1, revision=2,
                                              fingerprint="public-checkout-book-two",
                                              entries=[_entry(base="550.00")]))
        await publication.commit()
        release.set()
        with pytest.raises(HTTPException) as changed:
            await asyncio.wait_for(pending, timeout=10)
        assert changed.value.detail["code"] == "price_changed"
    async with factory() as verify:
        assert await verify.scalar(select(func.count(Order.id))) == 1
        assert await verify.scalar(select(func.count(OrderServiceLink.id))) == 1
