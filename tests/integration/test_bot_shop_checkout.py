"""Exercise the authenticated Telegram basket against native CRM orders and public offers."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from core.config import settings
from core.database import get_session
from models import Order, OrderProductLink, Product, StaffUser, TenantMembership
from models.personal_offer import PersonalOffer, PersonalOfferPublication
from models.tenancy import StorefrontDomain, utc_now
from routers.internal_bot_shop_actions import router
from routers.internal_bot_workspace import router as workspace_router


ROOT = "/api/internal/bot/v1/shop"
AUTH = {"Authorization": "Bearer checkout-test"}
ACTOR = {"telegram_id": 910071, "expected_context_version": 0}


@pytest.fixture
async def checkout_db(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        yield db


@pytest.fixture
async def checkout_client(db_engine):
    app = FastAPI()
    app.include_router(router)
    app.include_router(workspace_router)

    async def request_session():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = request_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def basket(checkout_db, monkeypatch):
    db = checkout_db
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "checkout-test")
    staff = StaffUser(display_name="Shop staff", roles=["manager"], primary_role="manager", telegram_id=ACTOR["telegram_id"])
    installer = StaffUser(display_name="Installer", roles=["installer"], primary_role="installer", telegram_id=910072)
    splits = [Product(title=f"Shop {i}", slug=f"shop-{i}", price=i * 1200, product_kind="complete_split_system",
                      is_published=True, main_image=f"/media/model-{i}.webp") for i in (1, 2)]
    db.add_all([staff, installer, *splits])
    await db.flush()
    db.add_all([
        TenantMembership(tenant_id=1, staff_user_id=staff.id, role="manager"),
        TenantMembership(tenant_id=1, staff_user_id=installer.id, role="installer"),
        StorefrontDomain(storefront_id=1, hostname="offers.example.test", status="active",
                         verified_at=utc_now(), is_primary=True),
    ])
    await db.commit()
    return [{"product_id": splits[0].id, "quantity": 2}, {"product_id": splits[1].id, "quantity": 3}]


@pytest.mark.parametrize("mode, proposals", [("bundle", 1), ("alternatives", 2)])
async def test_cart_creates_one_order_with_selected_quantities_on_retry(checkout_client, checkout_db, basket, mode, proposals):
    async_client, db = checkout_client, checkout_db
    data = {**ACTOR, "items": basket, "prospect_type": "company", "proposal_mode": mode, "idempotency_key": str(uuid4())}
    async def post(**overrides):
        return await async_client.post(ROOT + "/orders", json={**data, **overrides}, headers=AUTH)
    assert (await async_client.post(ROOT + "/orders", json=data)).status_code == 401
    assert (await post(telegram_id=910072)).status_code == 403
    assert (await post(expected_context_version=8)).status_code == 409
    assert (await post(items=[*basket, basket[0]])).status_code == 422
    assert (await post(items=[*basket, {"product_id": 99999, "quantity": 1}])).status_code == 422
    first, retry = await asyncio.gather(post(), post())
    assert first.status_code == retry.status_code == 200, (first.text, retry.text)
    assert retry.json() == first.json()
    order = await db.get(Order, first.json()["id"])
    assert order.status == "negotiation" and order.responsible_staff_user_id is not None
    rows = (await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order.id))).scalars().all()
    assert {r.product_id: (r.quantity, r.price) for r in rows} == {
        basket[0]["product_id"]: (2, 1200), basket[1]["product_id"]: (3, 2400),
    }
    assert len({r.proposal_id for r in rows}) == proposals
    detail = await async_client.get(f"/api/internal/bot/v1/workspace/orders/{order.id}", headers=AUTH, params=ACTOR)
    assert detail.status_code == 200, detail.text
    visible = detail.json()["proposals"]
    assert len(visible) == proposals and visible[0]["selected"]
    assert [(line["title"], line["quantity"], line["unit_price"]) for group in visible for line in group["equipment"]] == [
        ("Shop 1", 2, 1200), ("Shop 2", 3, 2400),
    ]


async def test_personal_link_is_scoped_priced_photographic_and_replayed(checkout_client, checkout_db, basket):
    async_client, db = checkout_client, checkout_db
    body = {**ACTOR, "items": basket, "title": "Для квартиры", "request_id": str(uuid4())}
    async def post(**overrides):
        return await async_client.post(ROOT + "/offers", headers=AUTH, json={**body, **overrides})
    assert (await post(telegram_id=910072)).status_code == 403
    assert (await post(expected_context_version=7)).status_code == 409
    assert (await post(items=[{**basket[0], "price_byn": 1}])).status_code == 422
    first, retry = await asyncio.gather(post(), post())
    assert first.status_code == retry.status_code == 200, (first.text, retry.text)
    assert retry.json() == first.json()
    assert first.json()["url"].startswith("https://offers.example.test/predlozhenie/")
    assert (await post()).json() == first.json()
    assert await db.scalar(select(func.count()).select_from(PersonalOffer)) == 1
    publication = (await db.execute(select(PersonalOfferPublication))).scalar_one()
    assert utc_now() + timedelta(days=6) < publication.expires_at <= utc_now() + timedelta(days=7)
    options = publication.snapshot["rooms"][0]["options"]
    assert float(options[0]["price_byn"]) == 1200 and "2400" in options[0]["note"]
    assert [o["main_image"] for o in options] == ["/media/model-1.webp", "/media/model-2.webp"]
    publication.revoked_at = utc_now()
    await db.commit()
    assert (await post()).status_code == 422
    assert await db.scalar(select(func.count()).select_from(PersonalOffer)) == 1
