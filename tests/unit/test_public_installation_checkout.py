"""Create-only installation checkout behavior with an isolated local database."""

from decimal import Decimal

import pytest
from sqlalchemy import delete
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, func, select

from models import (
    InstallationEstimate, InstallationEstimateRevision, InstallationPriceBook,
    IntegrationOutboxEvent,
    Order, OrderServiceLink, Product, PublicInstallationPreviewClaim, PublicWriteIdempotency,
    Storefront, Tenant,
)
from models.tenancy import TenantScope
from schemas_installation_price_book import InstallationPreviewPayload
from schemas_public_checkout import OrderPayload
from services.installation_price_book_service import InstallationPriceBookService
from services.website_order_service import WebsiteOrderService


def _entry():
    return {
        "tariff_id": 1, "code": "installation.wall.2_4", "mode": "fixed",
        "match": {"product_kind": "complete_split_system", "indoor_type": "wall",
                  "capacity_min_kw": "2", "capacity_max_kw": "4",
                  "pipe_liquid": '1/4"', "pipe_gas": '3/8"'},
        "base_price": "500.00", "short_name": "Монтаж", "description": "Монтаж",
        "included_route_m": "3", "included_holes": {"diamond": "1"},
        "rules": [
            {"id": 1, "code": "route.extra_m", "rule_type": "per_meter_over_included",
             "name": "Трасса", "line_template": "{name}", "unit": "м",
             "unit_price": "10.25", "is_optional": False, "sort_order": 1},
            {"id": 2, "code": "hole.diamond.extra", "rule_type": "per_hole_manual",
             "name": "Алмазное отверстие", "line_template": "{name}", "unit": "шт",
             "unit_price": "50.00", "is_optional": False, "sort_order": 2},
        ],
    }


@pytest.mark.asyncio
async def test_public_checkout_persists_one_exact_revision_and_replays_after_receipt_cleanup(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'checkout.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=301, storefront_id=302, is_system=True, is_canonical_storefront=True)
    try:
        async with factory() as session:
            session.add(Tenant(id=301, slug="public-checkout", display_name="Checkout", is_system=True))
            session.add(Storefront(id=302, tenant_id=301, slug="main", display_name="Main",
                                   status="active", is_default=True, currency="BYN"))
            product = Product(title="Wall AC", slug="wall-ac", price=2000,
                              product_kind="complete_split_system", is_published=True,
                              specs={"type": "wall", "indoor_type": "wall",
                                     "capacity_cooling_kw": "2.5", "pipe_liquid": '1/4"',
                                     "pipe_gas": '3/8"'})
            session.add(product)
            session.add(InstallationPriceBook(tenant_id=301, revision=1,
                                              fingerprint="checkout-book-one", entries=[_entry()]))
            await session.commit()
            preview = await InstallationPriceBookService.preview(
                session, scope, InstallationPreviewPayload.model_validate({
                    "installations": [{"key": "one", "product_id": product.id,
                                       "route_length_m": "6", "holes_by_type": {"diamond": 2}}],
                }), idempotency_key="checkout-preview-one-key",
            )
            assert preview.status == "fixed" and preview.total == Decimal("580.75")
            payload = OrderPayload.model_validate({
                "customer": {"name": "Test Buyer", "phone": "+375291112233"},
                "items": [{"product_id": product.id, "quantity": 1}],
                "installation_acceptance": {
                    "preview_ref": preview.preview_ref,
                    "expected_product_lines": [{"product_id": product.id, "quantity": 1,
                                                "unit_price": "2000.00", "currency": "BYN"}],
                    "expected_order_total": "2580.75",
                },
            })
            product.price = 2100
            session.add(product)
            await session.commit()
            with pytest.raises(HTTPException) as changed:
                await WebsiteOrderService.create_order(
                    session, payload, tenant_scope=scope,
                    idempotency_key="checkout-changed-one-key",
                )
            assert changed.value.status_code == 409
            assert changed.value.detail["code"] == "price_changed"
            assert changed.value.detail["reason"] == "product_price_changed"
            assert await session.scalar(select(func.count(Order.id))) == 0
            assert await session.scalar(select(func.count()).select_from(IntegrationOutboxEvent)) == 0
            product.price = 2000
            session.add(product)
            await session.commit()
            first = await WebsiteOrderService.create_order(
                session, payload, tenant_scope=scope,
                idempotency_key="checkout-submit-one-key",
            )
            assert Decimal(str(first.total_amount)) == Decimal("2580.75")
            await session.execute(delete(PublicWriteIdempotency))
            await session.commit()
            replay = await WebsiteOrderService.create_order(
                session, payload, tenant_scope=scope,
                idempotency_key="checkout-submit-one-key",
            )
            assert replay == first
            with pytest.raises(HTTPException) as reused:
                await WebsiteOrderService.create_order(
                    session, payload, tenant_scope=scope,
                    idempotency_key="checkout-other-one-key",
                )
            assert reused.value.detail["code"] == "preview_already_used"
            assert await session.scalar(select(func.count(Order.id))) == 1
            assert await session.scalar(select(func.count(InstallationEstimate.id))) == 1
            assert await session.scalar(select(func.count(InstallationEstimateRevision.id))) == 1
            assert await session.scalar(select(func.count(OrderServiceLink.id))) == 1
            assert await session.scalar(select(func.count(PublicInstallationPreviewClaim.id))) == 1
    finally:
        await engine.dispose()
