from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from models import (
    Customer,
    CustomerRequisitesRecognition,
    StaffUser,
    TenantMembership,
)
from models.tenancy import TenantScope
from services.bot_customer_requisites_api_service import (
    BotCustomerRequisitesAccessDeniedError,
    BotCustomerRequisitesApiService,
)

TEST_TENANT_SCOPE = TenantScope(
    tenant_id=1,
    storefront_id=1,
    is_system=True,
)


async def _add_manager(db, telegram_id: int) -> None:
    user = StaffUser(
        display_name=f"Manager {telegram_id}",
        status="active",
        roles=["manager"],
        primary_role="manager",
        telegram_id=telegram_id,
    )
    db.add(user)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(user.id),
            role="manager",
            status="active",
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_requisites_text_recognition_reuses_same_telegram_message(db, monkeypatch):
    await _add_manager(db, 2001)
    extract = AsyncMock(
        return_value={
            "name": "ООО Тест",
            "inn": "123456789",
            "phone": "+375291234567",
        }
    )
    monkeypatch.setattr(
        "services.customer_requisites_recognition_service.CustomerRequisitesRecognitionService.extract_requisites",
        extract,
    )

    kwargs = {
        "telegram_id": 2001,
        "text_value": "ООО Тест, УНП 123456789, банк и расчетный счет",
        "telegram_chat_id": -100,
        "telegram_message_id": 55,
        "tenant_scope": TEST_TENANT_SCOPE,
    }
    first = await BotCustomerRequisitesApiService.recognize_text_for_manager(db, **kwargs)
    repeated = await BotCustomerRequisitesApiService.recognize_text_for_manager(db, **kwargs)

    assert first["id"] == repeated["id"]
    assert extract.await_count == 1
    rows = (await db.execute(select(CustomerRequisitesRecognition))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_requisites_confirmation_is_idempotent_and_bound_to_owner(db):
    await _add_manager(db, 2002)
    await _add_manager(db, 2003)
    recognition = CustomerRequisitesRecognition(
        tenant_id=1,
        source="telegram_text",
        status="recognized",
        telegram_user_id=2002,
        telegram_chat_id=-100,
        telegram_message_id=77,
        raw_text="ООО Тест УНП 123456789",
        extracted_json={
            "name": "ООО Тест",
            "inn": "123456789",
            "phone": "+375291234567",
        },
        validation_flags={"field_errors": {}, "warnings": {}, "is_valid": True},
    )
    db.add(recognition)
    await db.commit()
    await db.refresh(recognition)

    first = await BotCustomerRequisitesApiService.apply_action_for_manager(
        db,
        telegram_id=2002,
        recognition_id=int(recognition.id),
        action="create",
        tenant_scope=TEST_TENANT_SCOPE,
    )
    repeated = await BotCustomerRequisitesApiService.apply_action_for_manager(
        db,
        telegram_id=2002,
        recognition_id=int(recognition.id),
        action="create",
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert first.changed is True
    assert repeated.changed is False
    assert repeated.customer["id"] == first.customer["id"]
    customers = (await db.execute(select(Customer))).scalars().all()
    assert len(customers) == 1

    with pytest.raises(BotCustomerRequisitesAccessDeniedError):
        await BotCustomerRequisitesApiService.apply_action_for_manager(
            db,
            telegram_id=2003,
            recognition_id=int(recognition.id),
            action="create",
            tenant_scope=TEST_TENANT_SCOPE,
        )
