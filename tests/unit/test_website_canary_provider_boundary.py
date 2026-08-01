from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    CommunicationDelivery,
    IntegrationOutboxEvent,
    StaffUser,
    TenantMembership,
)
from services.communications.delivery_materializer import (
    CommunicationDeliveryMaterializer,
)
from services.communications.delivery_service import ClaimedCommunicationDelivery
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.provider_boundary_authorization import (
    WebsiteCanaryProviderBoundaryRejected,
    authorize_website_provider_boundary,
)
from services.communications.template_registry import WebsiteTemplateRegistry
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
)
from services.communications.website_canary_target import WebsiteCanaryTarget
from tests.unit.tenant_website_test_support import (
    add_tenant_members,
    ensure_tenant_website_scope,
)


@pytest.fixture
async def boundary_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'website-boundary.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_boundary(session: AsyncSession):
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    await ensure_tenant_website_scope(session)
    owner = StaffUser(
        display_name="Boundary owner",
        status="active",
        roles=["owner"],
        primary_role="owner",
        telegram_id=1009,
    )
    await add_tenant_members(session, owner)
    assert owner.id is not None
    target = WebsiteCanaryTarget(
        event_id="2" * 32,
        event_type=TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
        tenant_id=1,
        storefront_id=1,
        recipient_key=f"staff:{owner.id}",
    )
    event = IntegrationOutboxEvent(
        event_id=target.event_id,
        event_type=target.event_type,
        schema_version=1,
        aggregate_type="lead",
        aggregate_id="32",
        aggregate_version=1,
        deduplication_key="website-boundary:32",
        payload={
            "tenant_id": 1,
            "storefront_id": 1,
            "lead_id": 32,
            "status": "new",
            "name": "Private",
            "phone": "+375290000000",
        },
        status="published",
        attempts=1,
        max_attempts=8,
        priority=20,
        available_at=now,
        occurred_at=now,
        published_at=now,
        created_at=now,
        updated_at=now,
    )
    plan = WebsiteTemplateRegistry.plan(event)
    delivery = CommunicationDelivery(
        delivery_id=CommunicationDeliveryMaterializer.build_delivery_id(
            event_id=event.event_id,
            channel=plan.channel,
            recipient_key=target.recipient_key,
            template_version=plan.template_version,
        ),
        event_id=event.event_id,
        channel=plan.channel,
        recipient_key=target.recipient_key,
        destination="1009",
        template_key=plan.template_key,
        template_version=plan.template_version,
        render_context=plan.render_context,
        status="running",
        priority=20,
        attempts=1,
        max_attempts=8,
        available_at=now,
        worker_id="boundary-worker",
        lease_token="x" * 32,
        lease_expires_at=now + timedelta(minutes=1),
        created_at=now,
        updated_at=now,
    )
    session.add_all([event, delivery])
    await session.commit()
    claim = ClaimedCommunicationDelivery(
        delivery_id=delivery.delivery_id,
        event_id=delivery.event_id,
        channel=delivery.channel,
        recipient_key=delivery.recipient_key,
        destination=delivery.destination,
        template_key=delivery.template_key,
        template_version=delivery.template_version,
        render_context=delivery.render_context,
        attempts=delivery.attempts,
        max_attempts=delivery.max_attempts,
        lease_token=delivery.lease_token or "",
        lease_expires_at=delivery.lease_expires_at or now,
    )
    scope = CommunicationProcessingScope.website_canary(
        run_id="11111111-1111-4111-8111-111111111111",
        control_revision=1,
        target=target,
    )
    return target, scope, claim


@pytest.mark.asyncio
async def test_boundary_rechecks_exact_locked_membership_and_destination(
    boundary_session_factory,
):
    async with boundary_session_factory() as session:
        target, scope, claim = await _seed_boundary(session)
        delivery = await session.get(CommunicationDelivery, claim.delivery_id)
        assert delivery is not None
        await authorize_website_provider_boundary(
            session,
            scope=scope,
            claim=claim,
            delivery=delivery,
        )

    async with boundary_session_factory() as session:
        membership = (
            await session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == target.tenant_id,
                    TenantMembership.staff_user_id
                    == int(target.recipient_key.split(":")[1]),
                )
            )
        ).scalar_one()
        membership.status = "suspended"
        await session.commit()
    async with boundary_session_factory() as session:
        delivery = await session.get(CommunicationDelivery, claim.delivery_id)
        assert delivery is not None
        with pytest.raises(WebsiteCanaryProviderBoundaryRejected):
            await authorize_website_provider_boundary(
                session,
                scope=scope,
                claim=claim,
                delivery=delivery,
            )

    async with boundary_session_factory() as session:
        membership = (
            await session.execute(select(TenantMembership))
        ).scalar_one()
        owner = await session.get(StaffUser, membership.staff_user_id)
        assert owner is not None
        membership.status = "active"
        owner.telegram_id = 1010
        await session.commit()
    async with boundary_session_factory() as session:
        delivery = await session.get(CommunicationDelivery, claim.delivery_id)
        assert delivery is not None
        with pytest.raises(WebsiteCanaryProviderBoundaryRejected):
            await authorize_website_provider_boundary(
                session,
                scope=scope,
                claim=claim,
                delivery=delivery,
            )


@pytest.mark.asyncio
async def test_boundary_rejects_claim_snapshot_drift(boundary_session_factory):
    async with boundary_session_factory() as session:
        _target, scope, claim = await _seed_boundary(session)
        delivery = await session.get(CommunicationDelivery, claim.delivery_id)
        assert delivery is not None
        with pytest.raises(WebsiteCanaryProviderBoundaryRejected):
            await authorize_website_provider_boundary(
                session,
                scope=scope,
                claim=replace(claim, channel="email"),
                delivery=delivery,
            )
