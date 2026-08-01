from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    ConsumerInbox,
    IntegrationOutboxEvent,
    StaffUser,
)
from services.communications.delivery_materializer import (
    CommunicationDeliveryMaterializer,
)
from services.communications.template_registry import (
    CONSUMER_NAME,
    HANDLER_VERSION,
    WebsiteTemplateRegistry,
)
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
)
from services.communications.website_canary_evidence import (
    WebsiteCanaryEvidenceRejected,
    classify_website_canary_evidence,
    load_website_canary_evidence,
)
from services.communications.website_canary_target import WebsiteCanaryTarget
from tests.unit.tenant_website_test_support import (
    add_tenant_members,
    ensure_tenant_website_scope,
)


@pytest.fixture
async def evidence_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'website-evidence.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_terminal_evidence(
    session: AsyncSession,
    *,
    delivery_status: str = "sent",
    attempt_outcome: str = "sent",
    ambiguous: bool = False,
) -> WebsiteCanaryTarget:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    await ensure_tenant_website_scope(session)
    owner = StaffUser(
        display_name="Canary owner",
        status="active",
        roles=["owner"],
        primary_role="owner",
        telegram_id=1009,
    )
    await add_tenant_members(session, owner)
    assert owner.id is not None
    target = WebsiteCanaryTarget(
        event_id="1" * 32,
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
        aggregate_id="31",
        aggregate_version=1,
        deduplication_key="website-evidence:31",
        payload={
            "tenant_id": 1,
            "storefront_id": 1,
            "lead_id": 31,
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
    delivery_id = CommunicationDeliveryMaterializer.build_delivery_id(
        event_id=event.event_id,
        channel=plan.channel,
        recipient_key=target.recipient_key,
        template_version=plan.template_version,
    )
    terminal_at = now if delivery_status in {"sent", "dead", "canceled"} else None
    session.add_all(
        [
            event,
            ConsumerInbox(
                consumer_name=CONSUMER_NAME,
                event_id=event.event_id,
                handler_version=HANDLER_VERSION,
                received_at=now,
                processed_at=now,
            ),
            CommunicationDelivery(
                delivery_id=delivery_id,
                event_id=event.event_id,
                channel=plan.channel,
                recipient_key=target.recipient_key,
                destination="1009",
                template_key=plan.template_key,
                template_version=plan.template_version,
                render_context=plan.render_context,
                status=delivery_status,
                priority=20,
                attempts=1,
                max_attempts=8,
                available_at=now,
                provider_message_id=(
                    "provider-1" if delivery_status == "sent" else None
                ),
                sent_at=now if delivery_status == "sent" else None,
                finished_at=terminal_at,
                created_at=now,
                updated_at=now,
            ),
            CommunicationDeliveryAttempt(
                delivery_id=delivery_id,
                attempt_no=1,
                started_at=now,
                finished_at=now,
                provider_started_at=now,
                outcome=attempt_outcome,
                error_category=(
                    "provider" if attempt_outcome in {"dead", "retry"} else None
                ),
                error_code=(
                    "provider_outcome_unknown"
                    if attempt_outcome in {"dead", "retry"}
                    else None
                ),
                ambiguous=ambiguous,
            ),
        ]
    )
    await session.commit()
    return target


@pytest.mark.asyncio
async def test_terminal_evidence_validates_full_deterministic_snapshot(
    evidence_session_factory,
):
    async with evidence_session_factory() as session:
        target = await _seed_terminal_evidence(session)
        evidence = await load_website_canary_evidence(
            session,
            target=target,
            lock=True,
        )

    assert evidence.render_context_fingerprint is not None
    assert len(evidence.render_context_fingerprint) == 64
    assert classify_website_canary_evidence(evidence) == ("terminal", "sent")


@pytest.mark.asyncio
async def test_ambiguous_attempt_has_priority_over_sent_delivery(
    evidence_session_factory,
):
    async with evidence_session_factory() as session:
        target = await _seed_terminal_evidence(
            session,
            attempt_outcome="dead",
            ambiguous=True,
        )
        evidence = await load_website_canary_evidence(
            session,
            target=target,
            lock=True,
        )

    assert classify_website_canary_evidence(evidence) == (
        "terminal",
        "ambiguous",
    )


@pytest.mark.asyncio
async def test_nonambiguous_contradictory_terminal_evidence_fails_closed(
    evidence_session_factory,
):
    async with evidence_session_factory() as session:
        target = await _seed_terminal_evidence(
            session,
            attempt_outcome="dead",
            ambiguous=False,
        )
        with pytest.raises(
            WebsiteCanaryEvidenceRejected,
            match="website_canary_attempt_snapshot_invalid",
        ):
            await load_website_canary_evidence(
                session,
                target=target,
                lock=True,
            )


@pytest.mark.asyncio
async def test_current_recipient_destination_drift_fails_closed(
    evidence_session_factory,
):
    async with evidence_session_factory() as session:
        target = await _seed_terminal_evidence(session)
        owner = await session.get(StaffUser, int(target.recipient_key.split(":")[1]))
        assert owner is not None
        owner.telegram_id = 1010
        await session.commit()
        with pytest.raises(
            WebsiteCanaryEvidenceRejected,
            match="website_canary_delivery_snapshot_invalid",
        ):
            await load_website_canary_evidence(
                session,
                target=target,
                lock=True,
            )
