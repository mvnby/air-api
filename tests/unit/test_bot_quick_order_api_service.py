from unittest.mock import AsyncMock

import pytest

from api_contracts.bot import BotQuickOrderDraft
from models import StaffUser
from services.bot_quick_order_api_service import (
    BotQuickOrderAccessDeniedError,
    BotQuickOrderApiService,
)


async def _add_staff(db, *, telegram_id: int, primary_role: str) -> None:
    db.add(
        StaffUser(
            display_name=f"Staff {telegram_id}",
            status="active",
            roles=[primary_role],
            primary_role=primary_role,
            telegram_id=telegram_id,
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
async def test_quick_order_api_uses_actor_scoped_idempotency_fingerprint(db, monkeypatch):
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
