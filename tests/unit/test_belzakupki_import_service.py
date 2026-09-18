from datetime import datetime, timezone

import pytest
from sqlmodel import select

from models import (
    BelzakupkiImportCheckpoint,
    LeadSource,
    Order,
    OrderStatus,
    Storefront,
    Tenant,
)
from services.belzakupki_import_service import BelzakupkiImportService
from services.order_service import OrderService
from services.tenant_scope_service import TenantScope


TENANT_SCOPE = TenantScope(
    tenant_id=1,
    storefront_id=1,
    is_system=True,
    is_canonical_storefront=True,
)
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _item(
    *,
    match_id: int = 10,
    profile_id: int = 7,
    external_id: str = "tender-42",
    score: float = 0.91,
    relevance_status: str = "confirmed",
    eligible: bool = True,
    deadline_at: str | None = "2026-10-01T10:00:00+00:00",
) -> dict:
    return {
        "id": match_id,
        "updated_at": "2026-09-19T10:00:00+00:00",
        "profile": {"id": profile_id, "name": "HVAC procurement"},
        "score": score,
        "relevance_status": relevance_status,
        "eligible": eligible,
        "reason": "Подходит по климатическому оборудованию",
        "ai_analysis": {"category": "hvac"},
        "tender": {
            "id": 500,
            "source": "belzakupki",
            "external_id": external_id,
            "title": "Поставка кондиционеров",
            "customer_name": "ОАО Заказчик",
            "url": "https://belzakupki.example/tender-42",
            "deadline_at": deadline_at,
            "published_at": "2026-09-18T10:00:00+00:00",
            "estimated_value": 120000,
            "contacts": [{"name": "Реальный контакт", "email": "contact@example.test"}],
            "ai_analysis": {"summary": "tender"},
        },
    }


@pytest.mark.asyncio
async def test_import_creates_order_in_inbox_without_customer_and_advances_cursor(db):
    result = await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={"items": [_item()], "next_cursor": "opaque-next", "has_more": True},
        cursor_before=None,
        now=NOW,
    )

    order = (await db.execute(select(Order))).scalar_one()
    checkpoint = (await db.execute(select(BelzakupkiImportCheckpoint))).scalar_one()

    assert result.created == 1
    assert order.customer_id is None
    assert order.status == OrderStatus.NEW_LEAD
    assert order.lead_source == LeadSource.BELZAKUPKI
    assert order.source_fingerprint == BelzakupkiImportService._order_fingerprint(
        source="belzakupki", external_id="tender-42"
    )
    assert order.technical_meta["belzakupki"]["tender"]["contacts"] == [
        {"name": "Реальный контакт", "email": "contact@example.test"}
    ]
    assert checkpoint.cursor == "opaque-next"


@pytest.mark.asyncio
async def test_import_is_idempotent_across_profiles_and_preserves_manager_fields(db):
    first = await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={
            "items": [_item(match_id=10, profile_id=7), _item(match_id=11, profile_id=8)],
            "next_cursor": "opaque-next",
            "has_more": True,
        },
        cursor_before=None,
        now=NOW,
    )
    order = (await db.execute(select(Order))).scalar_one()
    order.title = "Менеджер изменил заголовок"
    order.comment = "Менеджер добавил комментарий"
    order.status = OrderStatus.NEGOTIATION
    db.add(order)
    await db.commit()

    changed = _item(match_id=10, profile_id=7, score=0.99)
    second = await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={"items": [changed], "next_cursor": None, "has_more": False},
        cursor_before="opaque-next",
        now=NOW,
    )

    orders = list((await db.execute(select(Order))).scalars())
    checkpoint = (await db.execute(select(BelzakupkiImportCheckpoint))).scalar_one()
    assert first.created == 1
    assert first.updated == 1
    assert len(orders) == 1
    assert second.updated == 1
    assert orders[0].title == "Менеджер изменил заголовок"
    assert orders[0].comment == "Менеджер добавил комментарий"
    assert orders[0].status == OrderStatus.NEGOTIATION
    assert orders[0].technical_meta["belzakupki"]["matches"]["10"]["score"] == 0.99
    assert set(orders[0].technical_meta["belzakupki"]["matches"]) == {"10", "11"}
    assert checkpoint.cursor is None


@pytest.mark.asyncio
async def test_import_records_rejected_source_change_on_existing_order_without_creating_new_order(db):
    await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={"items": [_item()], "next_cursor": "cursor-1", "has_more": True},
        cursor_before=None,
        now=NOW,
    )
    rejected = _item(relevance_status="rejected", eligible=False)
    rejected["updated_at"] = "2026-09-19T11:00:00+00:00"
    result = await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={"items": [rejected], "next_cursor": None, "has_more": False},
        cursor_before="cursor-1",
        now=NOW,
    )

    orders = list((await db.execute(select(Order))).scalars())
    assert len(orders) == 1
    assert result.created == 0
    assert result.updated == 1
    assert orders[0].technical_meta["belzakupki"]["matches"]["10"]["relevance_status"] == "rejected"


@pytest.mark.asyncio
async def test_stale_page_does_not_process_or_advance_checkpoint(db):
    await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={"items": [], "next_cursor": "current", "has_more": True},
        cursor_before=None,
        now=NOW,
    )

    result = await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={"items": [_item()], "next_cursor": "stale-next", "has_more": True},
        cursor_before="older-cursor",
        now=NOW,
    )

    checkpoint = (await db.execute(select(BelzakupkiImportCheckpoint))).scalar_one()
    assert result.stale is True
    assert result.processed == 0
    assert result.cursor_after == "current"
    assert checkpoint.cursor == "current"


@pytest.mark.asyncio
async def test_import_excludes_ineligible_rejected_and_expired_items_but_commits_terminal_cursor(db):
    await BelzakupkiImportService.import_page(
        db, tenant_scope=TENANT_SCOPE,
        page={"items": [], "next_cursor": "previous", "has_more": True},
        cursor_before=None, now=NOW,
    )
    result = await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={
            "items": [
                _item(eligible=False),
                _item(match_id=11, relevance_status="rejected"),
                _item(match_id=12, deadline_at="2026-09-18T11:00:00+00:00"),
            ],
            "next_cursor": None,
            "has_more": False,
        },
        cursor_before="previous",
        now=NOW,
    )

    assert result.processed == 3
    assert result.accepted == 0
    assert result.skipped == 3
    assert list((await db.execute(select(Order))).scalars()) == []
    checkpoint = (await db.execute(select(BelzakupkiImportCheckpoint))).scalar_one()
    assert checkpoint.cursor is None


@pytest.mark.asyncio
async def test_import_failure_rolls_back_page_and_keeps_prior_checkpoint(db, monkeypatch):
    await BelzakupkiImportService.import_page(
        db,
        tenant_scope=TENANT_SCOPE,
        page={"items": [], "next_cursor": "previous", "has_more": True},
        cursor_before=None,
        now=NOW,
    )

    original_upsert = BelzakupkiImportService._upsert_opportunity

    async def fail_after_insert(*args, **kwargs):
        await original_upsert(*args, **kwargs)
        raise RuntimeError("simulated failure after order insert")

    monkeypatch.setattr(BelzakupkiImportService, "_upsert_opportunity", fail_after_insert)
    with pytest.raises(RuntimeError, match="simulated failure after order insert"):
        await BelzakupkiImportService.import_page(
            db,
            tenant_scope=TENANT_SCOPE,
            page={"items": [_item()], "next_cursor": "next", "has_more": True},
            cursor_before="previous",
            now=NOW,
        )

    assert list((await db.execute(select(Order))).scalars()) == []
    checkpoint = (await db.execute(select(BelzakupkiImportCheckpoint))).scalar_one()
    assert checkpoint.cursor == "previous"


@pytest.mark.asyncio
async def test_import_isolated_by_tenant_and_storefront(db):
    db.add(Tenant(id=2, slug="second", display_name="Second", status="active"))
    await db.flush()
    db.add(
        Storefront(
            id=2,
            tenant_id=2,
            slug="main",
            display_name="Second main",
            status="active",
            is_default=True,
        )
    )
    await db.commit()
    second_scope = TenantScope(
        tenant_id=2,
        storefront_id=2,
        is_system=False,
        is_canonical_storefront=True,
    )

    for scope in (TENANT_SCOPE, second_scope):
        await BelzakupkiImportService.import_page(
            db,
            tenant_scope=scope,
            page={"items": [_item()], "next_cursor": None, "has_more": False},
            cursor_before=None,
            now=NOW,
        )

    orders = list((await db.execute(select(Order).order_by(Order.tenant_id))).scalars())
    checkpoints = list(
        (await db.execute(select(BelzakupkiImportCheckpoint).order_by(BelzakupkiImportCheckpoint.tenant_id))).scalars()
    )
    assert [(order.tenant_id, order.storefront_id) for order in orders] == [(1, 1), (2, 2)]
    assert [(state.tenant_id, state.storefront_id) for state in checkpoints] == [(1, 1), (2, 2)]


def test_response_contract_rejects_cursor_inconsistency():
    with pytest.raises(ValueError, match="terminal page"):
        BelzakupkiImportService._validate_page(
            {"items": [], "has_more": False, "next_cursor": "not-allowed"}
        )


def test_initial_comment_uses_bounded_ai_explanation_when_reason_is_empty():
    comment = BelzakupkiImportService._initial_comment(
        {
            "reason": None,
            "ai_analysis": {"relevance_explanation": "Подходит для поставки HVAC."},
            "tender": {"title": "Поставка", "customer_name": "Заказчик"},
        }
    )

    assert "Причина соответствия: Подходит для поставки HVAC." in comment


def test_lead_inbox_uses_belzakupki_customer_name_without_creating_customer():
    order = Order(
        tenant_id=1,
        storefront_id=1,
        lead_source=LeadSource.BELZAKUPKI,
        technical_meta={"belzakupki": {"tender": {"customer_name": "  ОАО Заказчик  "}}},
    )

    assert order.customer_id is None
    assert OrderService._lead_inbox_customer_name(order) == "ОАО Заказчик"


def test_lead_inbox_does_not_apply_belzakupki_fallback_to_other_sources():
    order = Order(
        tenant_id=1,
        storefront_id=1,
        lead_source=LeadSource.EMAIL,
        technical_meta={"belzakupki": {"tender": {"customer_name": "Не показывать"}}},
    )

    assert OrderService._lead_inbox_customer_name(order) is None
