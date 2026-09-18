from unittest.mock import AsyncMock

import pytest

from api_contracts.bot import BotQuickOrderDraft
from models import Customer, CustomerType, Order, StaffUser, TenantMembership
from services.bot_quick_order_api_service import (
    BotQuickOrderAccessDeniedError,
    BotQuickOrderApiService,
)
from services.bot_quick_order_service import BotQuickOrderService


async def _add_staff(db, *, telegram_id: int, primary_role: str) -> None:
    staff_user = StaffUser(
        display_name=f"Staff {telegram_id}",
        status="active",
        roles=[primary_role],
        primary_role=primary_role,
        telegram_id=telegram_id,
    )
    db.add(staff_user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(staff_user.id),
            role=primary_role,
            status="active",
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_quick_order_api_parse_authorizes_manager_and_projects_stable_draft(db, monkeypatch):
    await _add_staff(db, telegram_id=1001, primary_role="manager")
    parse = AsyncMock(
        return_value={
            "name": "Иван",
            "phone": "+375291234567",
            "address": "Победы 15",
            "service_type": "maintenance",
            "target_date": "2026-07-20T14:00:00",
            "request_text": "ТО Иван завтра",
            "parser": "ai",
            "address_check": {
                "status": "confirmed",
                "message": "адрес найден",
                "suggestion": "проспект Победы, 15",
            },
            "private_field": "must not leak",
        }
    )
    monkeypatch.setattr(
        "services.bot_quick_order_api_service.BotQuickOrderService.parse_text",
        parse,
    )

    draft = await BotQuickOrderApiService.parse_for_manager(
        db,
        telegram_id=1001,
        text="ТО Иван завтра",
    )

    assert draft["service_label"] == "Обслуживание"
    assert draft["parser"] == "ai"
    assert draft["address_check"]["status"] == "confirmed"
    assert "private_field" not in draft


@pytest.mark.asyncio
async def test_quick_order_api_denies_executor(db):
    await _add_staff(db, telegram_id=1002, primary_role="installer")

    with pytest.raises(BotQuickOrderAccessDeniedError):
        await BotQuickOrderApiService.parse_for_manager(
            db,
            telegram_id=1002,
            text="Новый заказ",
        )


@pytest.mark.asyncio
async def test_quick_order_api_uses_actor_scoped_idempotency_fingerprint(
    db,
    monkeypatch,
    tenant_scope,
):
    await _add_staff(db, telegram_id=1003, primary_role="manager")
    create = AsyncMock(
        return_value={
            "id": 42,
            "customer": {"id": 7, "name": "Иван"},
            "_bot_order_created": False,
        }
    )
    monkeypatch.setattr(
        "services.bot_quick_order_api_service.BotQuickOrderService.create_order_from_draft",
        create,
    )
    draft = BotQuickOrderDraft(
        name="Иван",
        phone="+375291234567",
        service_type="maintenance",
        service_label="Обслуживание",
        request_text="ТО Иван",
    )

    result = await BotQuickOrderApiService.create_for_manager(
        db,
        telegram_id=1003,
        idempotency_key="telegram:-100:55",
        draft=draft,
    )

    assert result.order_id == 42
    assert result.customer_id == 7
    assert result.created is False
    assert create.await_args.kwargs["source_fingerprint"].startswith("bot_quick_order:v1:")
    assert create.await_args.kwargs["tenant_scope"] == tenant_scope
    sent_draft = create.await_args.args[1]
    assert "service_label" not in sent_draft


def test_quick_order_request_fingerprint_is_stable_and_actor_scoped():
    first = BotQuickOrderApiService._request_fingerprint(
        telegram_id=1003,
        idempotency_key="telegram:-100:55",
    )
    repeated = BotQuickOrderApiService._request_fingerprint(
        telegram_id=1003,
        idempotency_key="telegram:-100:55",
    )
    another_actor = BotQuickOrderApiService._request_fingerprint(
        telegram_id=1004,
        idempotency_key="telegram:-100:55",
    )

    assert first == repeated
    assert first != another_actor


@pytest.mark.parametrize(
    ("customer_type", "signing_mode"),
    [
        (CustomerType.company, "statutory_body"),
        (CustomerType.company, "power_of_attorney"),
        (CustomerType.individual_entrepreneur, "self"),
        (CustomerType.individual, "self"),
    ],
)
async def test_quick_order_preserves_existing_customer_party(db, tenant_scope, monkeypatch, customer_type, signing_mode):
    customer = Customer(
        tenant_id=tenant_scope.tenant_id,
        name="Клиент",
        phone="+375291234567",
        type=customer_type,
        signing_mode=signing_mode,
        inn="123456789" if customer_type != CustomerType.individual else None,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    monkeypatch.setattr(
        "services.bot_quick_order_service.NotificationService.notify_admins_staff_order_created",
        AsyncMock(),
    )

    result = await BotQuickOrderService.create_order_from_draft(
        db,
        {"name": "Клиент", "phone": customer.phone, "request_text": "Нужен новый заказ"},
        tenant_scope=tenant_scope,
    )

    await db.refresh(customer)
    order = await db.get(Order, result["id"])
    assert order.customer_id == customer.id
    assert customer.type == customer_type
    assert customer.signing_mode == signing_mode
