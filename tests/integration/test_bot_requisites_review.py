"""Exercise Telegram OCR review, ownership and concurrent actions through HTTP."""

import asyncio
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.database import get_session
from models import Customer, CustomerRequisitesRecognition, StaffUser, Storefront, Tenant, TenantMembership
from routers.internal_bot import router as business_router
from routers.internal_bot_context import router as context_router
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService as OCR


BASE = "/api/internal/bot/v1/customers/requisites"
OWNER = 10001
OTHER_MANAGER = 10002
INSTALLER = 10003
ACTOR = {"telegram_id": OWNER, "expected_context_version": 0}


@pytest.fixture
async def http(db_engine, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "requisites-test")
    monkeypatch.setattr(OCR, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(OCR, "extract_requisites", AsyncMock(return_value={
        "name": "ООО Клиент", "bank_name": "Новый банк",
    }))
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        tenant = Tenant(id=12, slug="partner", display_name="Partner")
        db.add(tenant)
        await db.flush()
        site = Storefront(
            tenant_id=12, slug="partner", display_name="Partner site", status="active", is_default=True,
        )
        db.add(site)
        for telegram_id, role in ((OWNER, "manager"), (OTHER_MANAGER, "manager"), (INSTALLER, "installer")):
            user = StaffUser(display_name=str(telegram_id), roles=[role], primary_role=role,
                             telegram_id=telegram_id)
            db.add(user)
            await db.flush()
            db.add(TenantMembership(tenant_id=1, staff_user_id=user.id, role=role))
            if telegram_id == OWNER:
                db.add(TenantMembership(tenant_id=12, staff_user_id=user.id, role=role))
        db.add_all([
            Customer(tenant_id=1, name="ООО Дубликат", inn="300063995", phone="", bank_name="Старый банк",
                     type="company", signing_mode="power_of_attorney"),
            Customer(tenant_id=12, name="Чужой клиент", inn="222222222", phone=""),
        ])
        await db.commit()

    app = FastAPI()
    app.include_router(context_router)
    app.include_router(business_router)

    async def request_session():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = request_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"Authorization": "Bearer requisites-test"}) as client:
        yield client


async def recognize(http):
    response = await http.post(f"{BASE}/recognize-text", json={**ACTOR, "text": "ООО Клиент реквизиты для договора"})
    assert response.status_code == 200, response.text
    return response.json()


async def edit(http, draft, fields):
    return await http.post(f"{BASE}/{draft['id']}/edit", json={
        **ACTOR, "expected_revision": draft["revision"], "fields": fields,
    })


async def action(http, draft, selected_action, *, versioned=True):
    payload = {**ACTOR, "action": selected_action}
    if versioned:
        payload["expected_revision"] = draft["revision"]
    return await http.post(f"{BASE}/{draft['id']}/action", json=payload)


async def test_draft_edits_revalidate_contacts_party_and_inn_without_writing_customers(http, db_engine):
    initial = await recognize(http)
    assert initial["extracted"]["customer_type"] == "company"
    response = await edit(http, initial, {"inn": "З00 063-995", "name": " ",
                                          "phone": "ошибка", "email": "ошибка"})
    assert response.status_code == 200, response.text
    invalid = response.json()
    assert invalid["duplicate_customer"]["name"] == "ООО Дубликат"
    assert invalid["extracted"]["inn"] == "300063995"
    assert invalid["validation_flags"]["is_valid"] is False
    assert set(invalid["validation_flags"]["field_errors"]) == {"name", "phone", "email"}
    assert (await action(http, invalid, "update")).status_code == 422

    response = await edit(http, invalid, {"customer_type": "individual_entrepreneur", "inn": "222222222"})
    assert response.status_code == 200
    still_invalid = response.json()
    assert still_invalid["duplicate_customer"] is None  # The same INN is in another tenant.
    assert set(still_invalid["validation_flags"]["field_errors"]) == {"name", "phone", "email"}
    response = await edit(http, still_invalid, {
        "name": "ООО Так напечатано", "full_legal_name": None, "email": " OK@Example.org ", "phone": "+375291234567",
    })
    assert response.status_code == 200
    final = response.json()
    assert final["validation_flags"] == {"field_errors": {}, "warnings": {}, "is_valid": True}
    assert final["extracted"]["customer_type"] == "individual_entrepreneur"
    assert final["extracted"]["email"] == "ok@example.org"
    assert final["extracted"]["full_legal_name"] is None
    for stale in (initial, invalid, still_invalid):
        assert (await action(http, stale, "create")).status_code == 409
    assert (await action(http, final, "create", versioned=False)).status_code == 409
    assert (await edit(http, invalid, {"name": "Гонка"})).status_code == 409

    async with AsyncSession(db_engine) as db:
        customers = (await db.execute(select(Customer).order_by(Customer.id))).scalars().all()
        assert [(c.name, c.bank_name) for c in customers] == [
            ("ООО Дубликат", "Старый банк"), ("Чужой клиент", None),
        ]
    confirmed = await action(http, final, "create")
    assert confirmed.status_code == 200, confirmed.text
    created = confirmed.json()
    assert created["changed"] is True
    assert created["recognition"]["revision"] == final["revision"]
    repeated = await action(http, final, "create")
    assert repeated.json()["changed"] is False
    assert repeated.json()["customer"] == created["customer"]
    assert (await action(http, initial, "create")).status_code == 409
    assert (await action(http, final, "cancel")).status_code == 409
    assert (await edit(http, final, {"name": "Поздно"})).status_code == 409
    async with AsyncSession(db_engine) as db:
        customer = await db.get(Customer, created["customer"]["id"])
        assert customer.type == "individual_entrepreneur" and customer.signing_mode == "self"
        assert customer.name == "ООО Так напечатано"
        assert customer.full_legal_name is None


@pytest.mark.parametrize("selected_action", ["update", "use"])
async def test_action_requires_current_duplicate_snapshot_and_replays_accepted_one(
    http, db_engine, monkeypatch, selected_action,
):
    monkeypatch.setattr(OCR, "extract_requisites", AsyncMock(return_value={
        "name": "ООО Клиент", "inn": "300063995", "bank_name": "Исправленный банк",
    }))
    draft = await recognize(http)
    target_id = draft["duplicate_customer"]["id"]
    async with AsyncSession(db_engine) as db:
        target = await db.get(Customer, target_id)
        target.bank_name = "Изменено в CRM"
        await db.commit()
    assert (await action(http, draft, selected_action)).status_code == 409
    assert (await action(http, draft, selected_action, versioned=False)).status_code == 409
    preview = await http.post(f"{BASE}/{draft['id']}/review", json=ACTOR)
    assert preview.status_code == 200
    reviewed = preview.json()
    assert reviewed["revision"] != draft["revision"]
    confirmed = await action(http, reviewed, selected_action)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["customer"]["id"] == target_id
    assert (await action(http, draft, selected_action)).status_code == 409
    async with AsyncSession(db_engine) as db:
        target = await db.get(Customer, target_id)
        assert target.signing_mode == "power_of_attorney"
        assert target.bank_name == ("Исправленный банк" if selected_action == "update" else "Изменено в CRM")
        target.bank_name = "Ещё одна правка после подтверждения"
        await db.commit()
    repeated = await action(http, reviewed, selected_action)
    assert repeated.json()["changed"] is False


async def test_changed_duplicate_identity_needs_new_preview_even_if_displayed_fields_match(http, db_engine, monkeypatch):
    monkeypatch.setattr(OCR, "extract_requisites", AsyncMock(return_value={
        "name": "ООО Клиент", "inn": "300063995",
    }))
    original = await recognize(http)
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        previous = await db.get(Customer, original["duplicate_customer"]["id"])
        previous.inn = None
        replacement = Customer(
            tenant_id=1, name=previous.name, phone=previous.phone, inn="300063995",
            type=previous.type, bank_name=previous.bank_name, signing_mode=previous.signing_mode,
        )
        db.add(replacement)
        await db.commit()
    assert (await action(http, original, "use")).status_code == 409
    reviewed = (await http.post(f"{BASE}/{original['id']}/review", json=ACTOR)).json()
    assert reviewed["duplicate_customer"]["id"] == replacement.id
    assert reviewed["revision"] != original["revision"]
    assert (await action(http, reviewed, "use")).json()["customer"]["id"] == replacement.id


async def test_untouched_chat_buttons_and_pre_release_duplicates(http, db_engine, monkeypatch):
    monkeypatch.setattr(OCR, "extract_requisites", AsyncMock(return_value={
        "name": "ООО Клиент", "inn": "300063995",
    }))
    current = await recognize(http)
    assert (await action(http, current, "use", versioned=False)).json()["changed"] is True
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        legacy = CustomerRequisitesRecognition(
            tenant_id=1, source="telegram_text", telegram_user_id=OWNER,
            extracted_json=current["extracted"], validation_flags=current["validation_flags"],
            duplicate_customer_id=current["duplicate_customer"]["id"],
        )
        db.add(legacy)
        await db.commit()
    reviewed = (await http.post(f"{BASE}/{legacy.id}/review", json=ACTOR)).json()
    assert (await action(http, reviewed, "use", versioned=False)).status_code == 409
    assert (await action(http, reviewed, "use")).json()["changed"] is True


async def test_telegram_origin_and_current_company_required_for_review_edit_and_action(http, db_engine):
    draft = await recognize(http)
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        unowned = CustomerRequisitesRecognition(tenant_id=1, source="telegram")
        manager = CustomerRequisitesRecognition(tenant_id=1, source="manager", telegram_user_id=OWNER)
        db.add_all([unowned, manager])
        await db.commit()
    for suffix, args in (
        ("review", {}), ("edit", {"fields": {"name": "Нет"}, "expected_revision": draft["revision"]}),
        ("action", {"action": "cancel"}),
    ):
        route = f"{BASE}/{draft['id']}/{suffix}"
        unauthenticated = await http.post(route, json={**ACTOR, **args}, headers={"Authorization": ""})
        assert unauthenticated.status_code == 401
        for denied_actor in (OTHER_MANAGER, INSTALLER, 123456789):
            denied = await http.post(route, json={**ACTOR, **args, "telegram_id": denied_actor})
            assert denied.status_code == 403, denied.text
        for other_id in (unowned.id, manager.id):
            denied = await http.post(f"{BASE}/{other_id}/{suffix}", json={**ACTOR, **args})
            assert denied.status_code == 403
    switched = await http.post("/api/internal/bot/v1/staff/context/select", json={
        **ACTOR, "tenant_id": 12, "storefront_slug": "partner",
    })
    assert switched.status_code == 200, switched.text
    for suffix, args in (("review", {}), ("edit", {"fields": {"name": "Нет"}, "expected_revision": draft["revision"]}),
                         ("action", {"action": "cancel"})):
        route = f"{BASE}/{draft['id']}/{suffix}"
        stale = await http.post(route, json={**ACTOR, **args})
        assert stale.status_code == 409
        other_tenant = await http.post(route, json={**ACTOR, **args, "expected_context_version": 1})
        assert other_tenant.status_code == 404


async def test_demo_company_can_read_its_ocr_preview_and_cannot_edit_or_apply(http, db_engine):
    draft = await recognize(http)
    async with AsyncSession(db_engine) as db:
        tenant = await db.get(Tenant, 1)
        tenant.demo_read_only = True
        await db.commit()
    read = await http.post(f"{BASE}/{draft['id']}/review", json=ACTOR)
    assert read.status_code == 200 and read.json()["revision"] == draft["revision"]
    assert (await edit(http, draft, {"name": "Недоступно"})).status_code == 403
    assert (await action(http, draft, "create")).status_code == 403


async def test_postgres_concurrent_edits_and_confirmations_are_serialized(http, db_engine):
    assert db_engine.dialect.name == "postgresql"
    initial = await recognize(http)
    responses = await asyncio.gather(*(edit(http, initial, {"name": name}) for name in ("Первый", "Второй")))
    assert sorted(r.status_code for r in responses) == [200, 409]
    draft = next(r.json() for r in responses if r.status_code == 200)
    # Reverting to the original values still invalidates the older buttons.
    reverted = (await edit(http, draft, {"name": initial["extracted"]["name"]})).json()
    assert reverted["extracted"] == initial["extracted"]
    assert reverted["revision"] != initial["revision"]
    assert (await action(http, initial, "create")).status_code == 409
    results = await asyncio.gather(*(action(http, reverted, "create") for _ in range(2)))
    assert all(r.status_code == 200 for r in results)
    assert sorted(r.json()["changed"] for r in results) == [False, True]
    assert len({r.json()["customer"]["id"] for r in results}) == 1


async def test_file_draft_can_be_corrected_and_cancelled_without_creating_a_customer(http, db_engine, monkeypatch):
    monkeypatch.setattr(OCR, "extract_ocr_text", AsyncMock(return_value="ООО Клиент реквизиты с документа"))
    response = await http.post(f"{BASE}/recognize-file", data=ACTOR,
                               files={"file": ("test.pdf", b"test-file", "application/pdf")})
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["source"] == "telegram"
    assert draft["raw_text"] == "ООО Клиент реквизиты с документа"
    assert "local_file_url" not in draft and "local_file_path" not in draft
    assert (await edit(http, draft, {"tenant_id": 12})).status_code == 422
    assert (await edit(http, draft, {"extra": {"forced": True}})).status_code == 422
    assert (await edit(http, draft, {})).status_code == 422
    assert (await edit(http, draft, {"customer_type": None})).status_code == 422
    assert (await edit(http, draft, {"name": "x" * 501})).status_code == 422
    updated = (await edit(http, draft, {"inn": "bad-inn"})).json()
    assert updated["validation_flags"]["is_valid"] is False
    assert (await action(http, updated, "cancel")).json()["changed"] is True
    assert (await action(http, updated, "cancel")).json()["changed"] is False
    assert (await action(http, updated, "create")).status_code == 409
    async with AsyncSession(db_engine) as db:
        assert len((await db.execute(select(Customer))).scalars().all()) == 2
