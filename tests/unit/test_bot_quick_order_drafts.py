from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api_contracts.bot import BotQuickOrderDraft
from services.bot_quick_order_draft_service import (
    BotQuickOrderDraftConflictError,
    BotQuickOrderDraftService,
)
from services.bot_quick_order_service import BotQuickOrderService


def _row() -> SimpleNamespace:
    return SimpleNamespace(
        storage_key="quick-order:" + "a" * 32,
        user_id=123,
        destiny="quick_order",
        state="active",
        updated_at=datetime.now(),
        data={
            "version": 1,
            "status": "active",
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
            "draft": BotQuickOrderDraft(
                name="ООО Пример",
                customer_type="company",
                workflow_type="maintenance",
                service_type="maintenance",
                service_label="Обслуживание",
                address="Витебск, Московский 10",
                request_text="Обслуживание",
            ).model_dump(mode="json"),
        },
    )


@pytest.mark.asyncio
async def test_draft_patch_changes_only_address_and_increments_version(monkeypatch):
    row = _row()
    monkeypatch.setattr(
        "services.bot_quick_order_draft_service.BotQuickOrderApiService._require_manager",
        AsyncMock(),
    )
    monkeypatch.setattr(BotQuickOrderDraftService, "_row", AsyncMock(return_value=row))
    session = SimpleNamespace(add=lambda _: None, commit=AsyncMock())

    result = await BotQuickOrderDraftService.patch(
        session,
        telegram_id=123,
        draft_id="a" * 32,
        expected_version=1,
        text=None,
        changes={"address": "Витебск, Московский 12А, корпус 2"},
    )

    assert result["version"] == 2
    assert result["draft"]["address"] == "Витебск, Московский 12А, корпус 2"
    assert result["draft"]["name"] == "ООО Пример"
    assert result["draft"]["service_type"] == "maintenance"
    assert result["draft"]["field_sources"]["address"] == "user"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_draft_patch_is_rejected_without_persistence(monkeypatch):
    row = _row()
    row.data["version"] = 2
    monkeypatch.setattr(
        "services.bot_quick_order_draft_service.BotQuickOrderApiService._require_manager",
        AsyncMock(),
    )
    monkeypatch.setattr(BotQuickOrderDraftService, "_row", AsyncMock(return_value=row))
    session = SimpleNamespace(add=lambda _: None, commit=AsyncMock())

    with pytest.raises(BotQuickOrderDraftConflictError):
        await BotQuickOrderDraftService.patch(
            session, telegram_id=123, draft_id="a" * 32,
            expected_version=1, text=None, changes={"address": "Старый адрес"},
        )
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_created_draft_retry_returns_same_order_without_create(monkeypatch):
    row = _row()
    row.data.update({"status": "created", "order_id": 44, "customer_id": 9})
    monkeypatch.setattr(
        "services.bot_quick_order_draft_service.BotQuickOrderApiService._require_manager",
        AsyncMock(),
    )
    monkeypatch.setattr(BotQuickOrderDraftService, "_row", AsyncMock(return_value=row))
    create = AsyncMock()
    monkeypatch.setattr(
        "services.bot_quick_order_draft_service.BotQuickOrderApiService.create_for_manager",
        create,
    )

    result = await BotQuickOrderDraftService.create(
        SimpleNamespace(), telegram_id=123, draft_id="a" * 32, expected_version=1
    )
    assert result == {"order_id": 44, "customer_id": 9, "created": False}
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_draft_patch_checks_manager_role(monkeypatch):
    require = AsyncMock(side_effect=PermissionError("manager required"))
    monkeypatch.setattr(
        "services.bot_quick_order_draft_service.BotQuickOrderApiService._require_manager",
        require,
    )
    with pytest.raises(PermissionError):
        await BotQuickOrderDraftService.patch(
            SimpleNamespace(), telegram_id=123, draft_id="a" * 32,
            expected_version=1, text=None, changes={},
        )


def test_fallback_keeps_full_city_street_house_and_apartment():
    draft = BotQuickOrderService.parse_text_fallback(
        "Витебск, ул. Ленина, 10, кв. 5"
    )
    assert draft["name"] is None
    assert draft["address"] == "Витебск, ул. Ленина, 10, кв. 5"


def test_fallback_address_after_po_adresu_has_no_trailing_u():
    draft = BotQuickOrderService.parse_text_fallback(
        "Нужно обслуживание по адресу Витебск, Московский 10"
    )
    assert draft["address"] == "Витебск, Московский 10"


def test_fallback_keeps_ip_when_bank_is_oao():
    draft = BotQuickOrderService.parse_text_fallback(
        "ИП Иванов Иван Иванович, монтаж своего кондиционера, банк ОАО Пример"
    )
    assert draft["customer_type"] == "individual_entrepreneur"
    assert draft["service_type"] == "install_only"


def test_fallback_separates_company_contact_and_equipment():
    draft = BotQuickOrderService.parse_text_fallback(
        "ООО Пример, обслуживание 3 кассетников, объект: Витебск, Московский 10, контакт Сергей"
    )
    assert draft["name"] == "ООО Пример"
    assert draft["contact_name"] == "Сергей"
    assert draft["equipment_count"] == 3
    assert draft["address"] == "Витебск, Московский 10"


def test_fallback_uses_first_object_and_preserves_full_request():
    text = "Монтаж, объект: Витебск, Московский 10; объект 2: Минск, Ленина 5"
    draft = BotQuickOrderService.parse_text_fallback(text)
    assert draft["address"] == "Витебск, Московский 10"
    assert "Минск, Ленина 5" in draft["request_text"]


@pytest.mark.asyncio
async def test_address_suggestion_with_same_number_stays_unconfirmed(monkeypatch):
    monkeypatch.setattr(
        "services.bot_quick_order_service.AddressSuggestService.suggest",
        AsyncMock(return_value=[{"value": "Минск, другая улица, 10"}]),
    )
    result = await BotQuickOrderService.enrich_draft(
        {"address": "Витебск, ул. Ленина, 10"}
    )
    assert result["address"] == "Витебск, ул. Ленина, 10"
    assert result["address_check"]["status"] == "needs_review"
