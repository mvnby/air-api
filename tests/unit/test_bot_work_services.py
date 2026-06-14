from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import StaffUser
from services.bot_access_service import BotAccessService
from services.bot_product_selection_service import BotProductSelectionService
from services.bot_quick_order_service import BotQuickOrderService
from services.product_service import ProductService
from bot_app.utils import format_caption


@pytest.fixture
async def sqlite_staff_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bot_staff.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_quick_order_fallback_parses_service_phone_address_and_date():
    draft = BotQuickOrderService.parse_text_fallback(
        "ТО, Иван, +375 29 123-45-67, Победы 15, завтра 14:00",
        now=datetime(2026, 6, 14, 10, 0),
    )

    assert draft["service_type"] == "maintenance"
    assert draft["phone"] == "+375 29 123-45-67"
    assert draft["name"] == "Иван"
    assert draft["address"] == "Победы 15"
    assert draft["target_date"] == "2026-06-15T14:00:00"


def test_product_caption_contains_public_product_link(monkeypatch):
    monkeypatch.setattr(
        "services.bot_product_selection_service.settings",
        SimpleNamespace(PUBLIC_SITE_URL="https://example.test"),
    )

    caption = format_caption(
        {
            "id": 1,
            "title": "Midea 12",
            "slug": "midea-12",
            "price": 1200,
            "area": 35,
            "description": "",
        }
    )

    assert "https://example.test/product/midea-12/" in caption


def test_product_selection_sorts_by_vitebsk_then_minsk_then_unknown():
    products = [
        {"id": 1, "price": 1000, "vitebsk_qty": 0, "minsk_qty": 0, "availability_status": "check_availability"},
        {"id": 2, "price": 1500, "vitebsk_qty": 0, "minsk_qty": 3, "availability_status": "available_2_3_days"},
        {"id": 3, "price": 1800, "vitebsk_qty": 1, "minsk_qty": 0, "availability_status": "in_stock_now"},
    ]

    sorted_products = BotProductSelectionService._sort_for_tier(products, "budget")

    assert [item["id"] for item in sorted_products] == [3, 2, 1]


def test_product_selection_parse_areas():
    assert BotProductSelectionService.parse_areas("подбор 20 м² и 35 квадратов") == [20, 35]


@pytest.mark.asyncio
async def test_bot_access_context_for_staff_and_non_staff(sqlite_staff_session):
    sqlite_staff_session.add(
        StaffUser(
            display_name="Менеджер",
            status="active",
            primary_role="manager",
            roles=["manager"],
            telegram_id=777,
        )
    )
    await sqlite_staff_session.commit()

    staff = await BotAccessService.get_context(sqlite_staff_session, 777)
    outsider = await BotAccessService.get_context(sqlite_staff_session, 888)

    assert staff.is_staff
    assert staff.is_manager
    assert staff.display_name == "Менеджер"
    assert not outsider.is_staff


@pytest.mark.asyncio
async def test_product_selection_builds_tiers(monkeypatch):
    async def fake_get_curated(session, area, is_inverter, limit=12, **kwargs):
        if is_inverter:
            return [
                {"id": area * 10 + 1, "title": f"Premium {area}", "slug": f"premium-{area}", "price": 2000, "vitebsk_qty": 0, "minsk_qty": 2},
                {"id": area * 10 + 2, "title": f"Optimal {area}", "slug": f"optimal-{area}", "price": 1500, "vitebsk_qty": 1, "minsk_qty": 0},
            ]
        return [
            {"id": area * 10 + 3, "title": f"Budget {area}", "slug": f"budget-{area}", "price": 1000, "vitebsk_qty": 1, "minsk_qty": 0}
        ]

    monkeypatch.setattr(ProductService, "get_curated", fake_get_curated)

    selection = await BotProductSelectionService.build_selection(object(), "20 и 35 м²")

    assert [area["area"] for area in selection["areas"]] == [20, 35]
    assert [tier["label"] for tier in selection["areas"][0]["tiers"]] == ["Бюджетнее", "Оптимально", "Премиум"]


@pytest.mark.asyncio
async def test_quick_order_create_uses_order_service_and_stage_for_dated_work(monkeypatch):
    calls = {}

    async def fake_create_manager_order(session, payload):
        calls["payload"] = payload
        return {"id": 42}

    async def fake_add_order_stage(session, order_id, payload):
        calls["stage_order_id"] = order_id
        calls["stage_payload"] = payload
        return {"id": order_id, "work_stages": [{"name": payload.name}]}

    monkeypatch.setattr(
        "services.bot_quick_order_service.OrderService.create_manager_order",
        fake_create_manager_order,
    )
    monkeypatch.setattr(
        "services.bot_quick_order_service.OrderService.add_order_stage",
        fake_add_order_stage,
    )

    order = await BotQuickOrderService.create_order_from_draft(
        object(),
        {
            "name": "Иван",
            "phone": "+375291234567",
            "address": "Победы 15",
            "service_type": "install_only",
            "target_date": "2026-06-15T14:00:00",
            "request_text": "Монтаж, Иван, Победы 15",
        },
    )

    assert order["id"] == 42
    assert calls["payload"].source == "bot"
    assert calls["payload"].service_type == "install_only"
    assert calls["stage_order_id"] == 42
    assert calls["stage_payload"].name == "Монтаж"
