from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.config import settings
from models import CommunicationDelivery, IntegrationOutboxEvent, StaffUser
from services.communications.contracts import (
    CommunicationRecipientV1,
    InstallationEstimateLeadCreatedPayloadV1,
    PublicContactLeadCreatedPayloadV1,
    PublicOrderCreatedPayloadV1,
    PublicOrderCustomerSnapshotV1,
    PublicOrderProductLineSnapshotV1,
    PublicOrderServiceLineSnapshotV1,
)
from services.communications.delivery_materializer import (
    CommunicationDeliveryMaterializer,
    DeliveryMaterializationConflict,
)
from services.communications.recipient_directory import ManagementRecipientDirectory
from services.communications.template_registry import (
    CONTACT_LEAD_TEMPLATE_KEY,
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    InvalidCommunicationEventPayload,
    WebsiteTemplateRegistry,
)


@pytest.fixture
async def communications_session_factory(tmp_path):
    database_path = tmp_path / "communications.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _lead_payload(*, lead_id: int = 12, message: str = "Нужна консультация"):
    return PublicContactLeadCreatedPayloadV1(
        lead_id=lead_id,
        status="new",
        name="Иван <b>не HTML</b>",
        phone="+375291112233",
        email="ivan@example.com",
        message=message,
    ).model_dump(mode="json")


def _event(
    sequence: int,
    *,
    event_type: str = "crm.public_contact_lead.created",
    payload: dict | None = None,
    now: datetime | None = None,
    priority: int = 100,
    max_attempts: int = 8,
) -> IntegrationOutboxEvent:
    occurred_at = now or datetime.now(timezone.utc)
    return IntegrationOutboxEvent(
        event_id=f"{sequence:032x}",
        event_type=event_type,
        schema_version=1,
        aggregate_type="lead",
        aggregate_id=str(sequence),
        aggregate_version=1,
        deduplication_key=f"test:{sequence}",
        payload=payload if payload is not None else _lead_payload(lead_id=sequence),
        priority=priority,
        max_attempts=max_attempts,
        available_at=occurred_at,
        occurred_at=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _owner(telegram_id: int, *, status: str = "active", name: str = "Owner"):
    return StaffUser(
        display_name=name,
        status=status,
        roles=["owner"],
        primary_role="owner",
        telegram_id=telegram_id,
    )


@pytest.mark.asyncio
async def test_recipient_directory_prefers_eligible_staff_and_filters_roles(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    async with communications_session_factory() as session:
        session.add_all(
            [
                _owner(101, name="Owner"),
                StaffUser(
                    display_name="Manager",
                    status="active",
                    roles=["manager"],
                    primary_role="manager",
                    telegram_id=202,
                ),
                _owner(303, status="blocked", name="Blocked"),
                StaffUser(
                    display_name="Installer",
                    status="active",
                    roles=["installer"],
                    primary_role="installer",
                    telegram_id=404,
                ),
            ]
        )
        await session.flush()

        recipients = await ManagementRecipientDirectory.list_telegram(session)

        assert [recipient.destination for recipient in recipients] == ["101", "202"]
        assert all(recipient.source == "staff" for recipient in recipients)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "primary_role"),
    [
        ("blocked", "owner"),
        ("inactive", "owner"),
        ("active", "installer"),
    ],
)
async def test_recipient_directory_legacy_fallback_cannot_reenable_ineligible_staff(
    communications_session_factory,
    monkeypatch,
    status,
    primary_role,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "303,707", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    async with communications_session_factory() as session:
        session.add(
            StaffUser(
                display_name="Ineligible",
                status=status,
                roles=[primary_role],
                primary_role=primary_role,
                telegram_id=303,
            )
        )
        await session.flush()

        recipients = await ManagementRecipientDirectory.list_telegram(session)

        assert [recipient.destination for recipient in recipients] == ["707"]
        assert recipients[0].recipient_key == "legacy-telegram:707"


@pytest.mark.asyncio
async def test_recipient_directory_propagates_database_failure(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "707", raising=False)
    session = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("db down")))

    with pytest.raises(RuntimeError, match="db down"):
        await ManagementRecipientDirectory.list_telegram(session)


def test_template_registry_validates_escapes_and_bounds_telegram_html():
    event = _event(12, payload=_lead_payload(message="line\x00one\nline two"))
    plan = WebsiteTemplateRegistry.plan(event)
    rendered = WebsiteTemplateRegistry.render(plan)

    assert plan.template_key == CONTACT_LEAD_TEMPLATE_KEY
    assert plan.audience == "management"
    assert "&lt;b&gt;не HTML&lt;/b&gt;" in rendered
    assert "<b>не HTML</b>" not in rendered
    assert "\x00" not in rendered
    assert "lineone line two" in rendered
    assert len(rendered) <= 4096

    with pytest.raises(InvalidCommunicationEventPayload):
        WebsiteTemplateRegistry.plan(_event(13, payload={"lead_id": 13}))


def test_v1_templates_have_stable_golden_output():
    lead = _event(
        1,
        payload=PublicContactLeadCreatedPayloadV1(
            lead_id=1,
            status="new",
            name="Иван & Анна",
            phone="+375291112233",
            message="Хочу расчёт",
        ).model_dump(mode="json"),
    )
    assert WebsiteTemplateRegistry.render(WebsiteTemplateRegistry.plan(lead)) == (
        "🔔 <b>ЗАЯВКА С САЙТА #1</b>\n"
        "👤 Иван &amp; Анна\n"
        "📱 +375291112233\n\n"
        "💬 Хочу расчёт"
    )

    order_payload = PublicOrderCreatedPayloadV1(
        order_id=2,
        status="new",
        customer=PublicOrderCustomerSnapshotV1(
            name="Иван",
            phone="+375291112233",
        ),
        total_amount=Decimal("125.50"),
        product_lines=[
            PublicOrderProductLineSnapshotV1(
                product_id=7,
                title="Сплит <7>",
                quantity=1,
                unit_price=Decimal("100"),
                installation_included=True,
                installation_price=Decimal("20"),
            )
        ],
        service_lines=[
            PublicOrderServiceLineSnapshotV1(
                service_id=8,
                title="Доставка",
                quantity=1,
                unit_price=Decimal("5.50"),
            )
        ],
    )
    order = _event(
        2,
        event_type="crm.public_order.created",
        payload=order_payload.model_dump(mode="json"),
    )
    assert WebsiteTemplateRegistry.render(WebsiteTemplateRegistry.plan(order)) == (
        "🌐 <b>ЗАКАЗ С САЙТА #2</b>\n"
        "👤 Иван\n"
        "📱 +375291112233\n\n"
        "🛒 <b>Товары:</b>\n"
        "▫️ Сплит &lt;7&gt; x1 — 100 BYN\n"
        "   └ 🔧 Монтаж: 20 BYN\n"
        "🔧 Доставка x1 — 5.5 BYN\n\n"
        "💰 <b>Итого: 125.5 BYN</b>"
    )

    estimate = _event(
        3,
        event_type=INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
        payload=InstallationEstimateLeadCreatedPayloadV1(
            order_id=3,
            status="new_lead",
            name="Анна & Иван",
            phone="+375291112233",
            address="Минск <центр>",
            description="Нужна предварительная оценка",
            attachment_count=2,
            photo_categories=("Место внутреннего блока", "Трасса"),
        ).model_dump(mode="json"),
    )
    assert WebsiteTemplateRegistry.render(WebsiteTemplateRegistry.plan(estimate)) == (
        "📷 <b>МОНТАЖ ПО ФОТО #3</b>\n"
        "👤 Анна &amp; Иван\n"
        "📱 +375291112233\n"
        "📍 Минск &lt;центр&gt;\n\n"
        "💬 Нужна предварительная оценка\n\n"
        "🖼 Фото: 2\n"
        "Категории: Место внутреннего блока, Трасса\n"
        "Статус: ожидает предварительной оценки"
    )


def test_order_template_caps_detail_rows_and_stays_within_telegram_limit():
    payload = PublicOrderCreatedPayloadV1(
        order_id=44,
        status="new",
        customer=PublicOrderCustomerSnapshotV1(
            name="Иван",
            phone="+375291112233",
        ),
        comment="<&>" * 600,
        total_amount=Decimal("9000"),
        product_lines=[
            PublicOrderProductLineSnapshotV1(
                product_id=index + 1,
                title=f"Товар {index} " + "<&>" * 50,
                quantity=1,
                unit_price=Decimal("100"),
            )
            for index in range(20)
        ],
        service_lines=[
            PublicOrderServiceLineSnapshotV1(
                service_id=index + 1,
                title=f"Услуга {index} " + "<&>" * 50,
                quantity=1,
                unit_price=Decimal("50"),
            )
            for index in range(20)
        ],
    )
    event = _event(
        44,
        event_type="crm.public_order.created",
        payload=payload.model_dump(mode="json"),
    )

    rendered = WebsiteTemplateRegistry.render(WebsiteTemplateRegistry.plan(event))

    assert "… ещё товаров: 14" in rendered
    assert "… ещё услуг: 16" in rendered
    assert len(rendered) <= 4096


@pytest.mark.asyncio
async def test_materializer_is_idempotent_and_rejects_immutable_snapshot_drift(
    communications_session_factory,
):
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    event = _event(18, now=now)
    plan = WebsiteTemplateRegistry.plan(event)
    recipient = CommunicationRecipientV1(
        recipient_key="legacy-telegram:700",
        destination="700",
        source="legacy",
    )
    async with communications_session_factory() as session:
        session.add(event)
        await session.commit()

        first = await CommunicationDeliveryMaterializer.materialize(
            session,
            event=event,
            plan=plan,
            recipients=[recipient],
            now=now,
        )
        await session.commit()
        duplicate = await CommunicationDeliveryMaterializer.materialize(
            session,
            event=event,
            plan=plan,
            recipients=[recipient],
            now=now + timedelta(minutes=1),
        )

        assert first.created_count == 1
        assert duplicate.created_count == 0
        with pytest.raises(DeliveryMaterializationConflict):
            await CommunicationDeliveryMaterializer.materialize(
                session,
                event=event,
                plan=plan,
                recipients=[recipient.model_copy(update={"destination": "701"})],
                now=now,
            )


@pytest.mark.asyncio
async def test_materializer_rejects_recipient_set_drift_without_partial_rows(
    communications_session_factory,
):
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    event = _event(19, now=now)
    plan = WebsiteTemplateRegistry.plan(event)
    recipient_a = CommunicationRecipientV1(
        recipient_key="legacy-telegram:700",
        destination="700",
        source="legacy",
    )
    recipient_b = CommunicationRecipientV1(
        recipient_key="legacy-telegram:701",
        destination="701",
        source="legacy",
    )
    recipient_c = CommunicationRecipientV1(
        recipient_key="legacy-telegram:702",
        destination="702",
        source="legacy",
    )
    async with communications_session_factory() as session:
        session.add(event)
        await session.flush()
        await CommunicationDeliveryMaterializer.materialize(
            session,
            event=event,
            plan=plan,
            recipients=[recipient_a, recipient_b],
            now=now,
        )
        await session.commit()

        with pytest.raises(DeliveryMaterializationConflict):
            await CommunicationDeliveryMaterializer.materialize(
                session,
                event=event,
                plan=plan,
                recipients=[recipient_a, recipient_c],
                now=now,
            )
        await session.rollback()

        destinations = list(
            (
                await session.execute(
                    select(CommunicationDelivery.destination).order_by(
                        CommunicationDelivery.destination
                    )
                )
            ).scalars()
        )
        assert destinations == ["700", "701"]
