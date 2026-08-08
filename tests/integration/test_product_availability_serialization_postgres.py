from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import IntegrationOutboxEvent, Order, Product, PublicWriteIdempotency
from schemas import ProductAvailabilityLeadPayload
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_AVAILABILITY_REQUESTED_EVENT,
)
from services.public_write_idempotency_service import (
    PublicWriteIdempotencyService,
)
from services.tenant_scope_service import TenantScope
from services.website_lead_service import WebsiteLeadService


@pytest.mark.asyncio
async def test_distinct_keys_serialize_to_one_availability_order_and_event(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as setup:
        order_count_before = int(
            await setup.scalar(select(func.count(Order.id))) or 0
        )
        product = Product(
            title="Availability serialization product",
            slug="availability-serialization-product",
            price=1200,
            is_published=True,
        )
        setup.add(product)
        await setup.commit()
        await setup.refresh(product)
        product_id = int(product.id or 0)

    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    barrier = asyncio.Barrier(2)
    keys = (
        "availability-serialization-key-0001",
        "availability-serialization-key-0002",
    )

    async def submit(key: str, phone: str):
        async with factory() as session:
            await barrier.wait()
            return await WebsiteLeadService.create_product_availability_lead(
                session,
                ProductAvailabilityLeadPayload(
                    product_id=product_id,
                    phone=phone,
                    name="Availability concurrency",
                ),
                tenant_scope=scope,
                idempotency_key=key,
            )

    first, second = await asyncio.gather(
        submit(keys[0], "+375 (29) 777-11-22"),
        submit(keys[1], "8 (029) 777-11-22"),
    )

    assert first.lead_id == second.lead_id
    async with factory() as verification:
        order = await verification.get(Order, first.lead_id)
        event_count = await verification.scalar(
            select(func.count(IntegrationOutboxEvent.event_id)).where(
                IntegrationOutboxEvent.event_type
                == TENANT_WEBSITE_AVAILABILITY_REQUESTED_EVENT,
                IntegrationOutboxEvent.aggregate_id == str(first.lead_id),
            )
        )
        receipt_count = await verification.scalar(
            select(func.count(PublicWriteIdempotency.id)).where(
                PublicWriteIdempotency.command_name
                == "public_product_availability_lead_v1",
                PublicWriteIdempotency.key_hash.in_(
                    [
                        PublicWriteIdempotencyService.key_hash(key)
                        for key in keys
                    ]
                ),
            )
        )
        order_count_after = int(
            await verification.scalar(select(func.count(Order.id))) or 0
        )

    assert order is not None
    assert order_count_after == order_count_before + 1
    assert order.technical_meta["availability_product_id"] == product_id
    assert order.technical_meta["availability_last_notified_at"]
    assert event_count == 1
    assert receipt_count == 2
