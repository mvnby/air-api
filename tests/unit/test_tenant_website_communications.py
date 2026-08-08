from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import IntegrationOutboxEvent, StaffUser, Storefront, Tenant, TenantMembership
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import (
    PublicOrderCustomerSnapshotV1,
    TenantWebsiteCheckoutCreatedPayloadV1,
)
from services.communications.recipient_directory import (
    TenantWebsiteManagementRecipientDirectory,
)
from services.communications.template_registry import WebsiteTemplateRegistry
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
    TENANT_WEBSITE_CHECKOUT_TEMPLATE_KEY,
)


@pytest.fixture
async def tenant_website_session(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'tenant-website.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


def _staff(name: str, telegram_id: int | None) -> StaffUser:
    return StaffUser(
        display_name=name,
        status="active",
        roles=["owner"],
        primary_role="owner",
        telegram_id=telegram_id,
    )


@pytest.mark.asyncio
async def test_tenant_website_directory_has_no_cross_tenant_or_legacy_fallback(
    tenant_website_session,
    monkeypatch,
):
    session = tenant_website_session
    monkeypatch.setenv("ADMIN_IDS", "999001,999002")
    session.add_all(
        [
            Tenant(id=1, slug="one", display_name="One", status="active"),
            Tenant(id=2, slug="two", display_name="Two", status="active"),
            Storefront(
                id=1,
                tenant_id=1,
                slug="main",
                display_name="One Main",
                status="active",
                is_default=True,
            ),
            Storefront(
                id=2,
                tenant_id=2,
                slug="main",
                display_name="Two Main",
                status="active",
                is_default=True,
            ),
        ]
    )
    owner = _staff("Tenant one owner", 101001)
    admin = _staff("Tenant one admin", 101002)
    manager = _staff("Tenant one manager", 101003)
    other_owner = _staff("Tenant two owner", 202001)
    session.add_all([owner, admin, manager, other_owner])
    await session.flush()
    session.add_all(
        [
            TenantMembership(
                tenant_id=1,
                staff_user_id=int(owner.id or 0),
                role="owner",
                status="active",
            ),
            TenantMembership(
                tenant_id=1,
                staff_user_id=int(admin.id or 0),
                role="admin",
                status="active",
            ),
            TenantMembership(
                tenant_id=1,
                staff_user_id=int(manager.id or 0),
                role="manager",
                status="active",
            ),
            TenantMembership(
                tenant_id=2,
                staff_user_id=int(other_owner.id or 0),
                role="owner",
                status="active",
            ),
        ]
    )
    await session.flush()

    recipients = await TenantWebsiteManagementRecipientDirectory.list_telegram(
        session,
        tenant_id=1,
        storefront_id=1,
    )

    assert [recipient.destination for recipient in recipients] == [
        "101001",
        "101002",
    ]
    assert all(recipient.source == "staff" for recipient in recipients)


@pytest.mark.asyncio
async def test_tenant_website_directory_rejects_cross_tenant_storefront_pair(
    tenant_website_session,
):
    session = tenant_website_session
    session.add_all(
        [
            Tenant(id=1, slug="one", display_name="One", status="active"),
            Tenant(id=2, slug="two", display_name="Two", status="active"),
            Storefront(
                id=2,
                tenant_id=2,
                slug="main",
                display_name="Two Main",
                status="active",
                is_default=True,
            ),
        ]
    )
    await session.flush()

    with pytest.raises(
        CommunicationsCanarySafetyError,
        match="tenant_website_scope_invalid",
    ):
        await TenantWebsiteManagementRecipientDirectory.list_telegram(
            session,
            tenant_id=1,
            storefront_id=2,
        )


def test_tenant_website_event_contract_and_registry_are_strict():
    with pytest.raises(ValidationError):
        TenantWebsiteCheckoutCreatedPayloadV1.model_validate(
            {
                "order_id": 7,
                "status": "negotiation",
                "customer": {"name": "Иван", "phone": "+375291112233"},
                "total_amount": 100,
            }
        )

    payload = TenantWebsiteCheckoutCreatedPayloadV1(
        tenant_id=1,
        storefront_id=3,
        order_id=7,
        status="negotiation",
        customer=PublicOrderCustomerSnapshotV1(
            name="Иван",
            phone="+375291112233",
        ),
        total_amount=100,
    )
    now = datetime.now(timezone.utc)
    event = IntegrationOutboxEvent(
        event_id="a" * 32,
        event_type=TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
        schema_version=1,
        aggregate_type="order",
        aggregate_id="7",
        deduplication_key="tenant-website-checkout-test",
        payload=payload.model_dump(mode="json"),
        available_at=now,
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )

    plan = WebsiteTemplateRegistry.plan(event)

    assert plan.template_key == TENANT_WEBSITE_CHECKOUT_TEMPLATE_KEY
    assert plan.audience == "tenant_website_management"
    assert plan.render_context["tenant_id"] == 1
