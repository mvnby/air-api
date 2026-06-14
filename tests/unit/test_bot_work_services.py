from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from crud.product import ProductDAO
from models import StaffUser
from services.bot_access_service import BotAccessService
from services.bot_product_selection_service import BotProductSelectionService
from services.bot_quick_order_service import BotQuickOrderService
from services.product_read_service import ProductReadService
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


def test_product_selection_parse_power_classes_preserves_repeats():
    parsed = BotProductSelectionService.parse_selection_request("подбор 7,7,12")

    assert [target["code"] for target in parsed["targets"]] == ["7", "7", "12"]
    assert [target["kw"] for target in parsed["targets"]] == [1.9, 1.9, 3.5]
    assert parsed["targets"][0]["label"] == "7 (1,9 кВт)"
    assert parsed["compressor_mode"] == "mixed"


def test_product_selection_parse_power_class_words_and_inverter_mode():
    parsed = BotProductSelectionService.parse_selection_request("нужно две семёрки и двенашка, инвертора")

    assert [target["code"] for target in parsed["targets"]] == ["7", "7", "12"]
    assert parsed["compressor_mode"] == "inverter_only"
    assert parsed["mode_reason"] == "инверторы"


def test_product_selection_parse_server_room_forces_onoff_mode():
    parsed = BotProductSelectionService.parse_selection_request("серверная, 7 и 12, только on-off")

    assert [target["code"] for target in parsed["targets"]] == ["7", "12"]
    assert parsed["compressor_mode"] == "onoff_only"
    assert parsed["mode_reason"] == "серверная"


def test_product_selection_parse_non_inverter_wording_forces_onoff_mode():
    for query in ("не инвертор 12", "не инверторный 12", "on/off 12"):
        parsed = BotProductSelectionService.parse_selection_request(query)

        assert [target["code"] for target in parsed["targets"]] == ["12"]
        assert parsed["compressor_mode"] == "onoff_only"
        assert parsed["mode_reason"] == "ON-OFF"


def test_product_selection_parse_limits_word_repeats():
    parsed = BotProductSelectionService.parse_selection_request(
        "две семерки две девятки две двенашки две восемнашки"
    )

    assert [target["code"] for target in parsed["targets"]] == ["7", "7", "9", "9", "12", "12"]


def test_product_selection_parse_compact_quantity_syntax():
    cases = {
        "2x7 и 12": ["7", "7", "12"],
        "2х7 и 12": ["7", "7", "12"],
        "2*7, 3 шт 12": ["7", "7", "12", "12", "12"],
        "7x2 и 12х3": ["7", "7", "12", "12", "12"],
        "две 7 и один 12": ["7", "7", "12"],
        "4 штуки 9": ["9", "9", "9", "9"],
    }

    for query, expected_codes in cases.items():
        parsed = BotProductSelectionService.parse_selection_request(query)

        assert [target["code"] for target in parsed["targets"]] == expected_codes


def test_product_selection_parse_limits_compact_quantity_syntax():
    parsed = BotProductSelectionService.parse_selection_request("4x7 4x12")

    assert [target["code"] for target in parsed["targets"]] == ["7", "7", "7", "7", "12", "12"]


def test_product_selection_parse_does_not_treat_large_area_as_quantity():
    parsed = BotProductSelectionService.parse_selection_request("20 12")

    assert [target.get("code") for target in parsed["targets"]] == [None, "12"]
    assert parsed["targets"][0]["label"] == "20 м²"


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
async def test_product_selection_builds_power_classes_and_inverter_only(monkeypatch):
    calls = []

    async def fake_get_curated(session, area, is_inverter, limit=12, **kwargs):
        calls.append(
            {
                "area": area,
                "area_min": kwargs.get("area_min"),
                "area_max": kwargs.get("area_max"),
                "is_inverter": is_inverter,
                "tag_slugs": kwargs.get("tag_slugs"),
            }
        )
        return [
            {
                "id": len(calls),
                "title": f"Picked {area}",
                "slug": f"picked-{area}-{len(calls)}",
                "price": 1500,
                "vitebsk_qty": 1,
                "minsk_qty": 0,
            }
        ]

    monkeypatch.setattr(ProductService, "get_curated", fake_get_curated)

    selection = await BotProductSelectionService.build_selection(object(), "7,12 инвертора")

    assert [area["label"] for area in selection["areas"]] == ["7 (1,9 кВт)", "12 (3,5 кВт)"]
    assert [tier["key"] for tier in selection["areas"][0]["tiers"]] == ["optimal", "premium"]
    assert {call["is_inverter"] for call in calls} == {True}
    assert calls[0]["area_min"] == 15
    assert calls[0]["area_max"] == 24
    assert calls[0]["tag_slugs"] == ["cat-household"]


@pytest.mark.asyncio
async def test_product_selection_builds_onoff_only_for_server_room(monkeypatch):
    calls = []

    async def fake_get_curated(session, area, is_inverter, limit=12, **kwargs):
        calls.append({"is_inverter": is_inverter, "area_min": kwargs.get("area_min"), "area_max": kwargs.get("area_max")})
        return [
            {
                "id": 1,
                "title": "Server ON-OFF",
                "slug": "server-onoff",
                "price": 1000,
                "vitebsk_qty": 1,
                "minsk_qty": 0,
            }
        ]

    monkeypatch.setattr(ProductService, "get_curated", fake_get_curated)

    selection = await BotProductSelectionService.build_selection(object(), "серверная 12")
    formatted = BotProductSelectionService.format_selection(selection)

    assert [tier["key"] for tier in selection["areas"][0]["tiers"]] == ["onoff"]
    assert calls == [{"is_inverter": False, "area_min": 33, "area_max": 42}]
    assert "Режим: только ON-OFF (серверная)" in formatted


@pytest.mark.asyncio
async def test_product_read_curated_passes_power_range_to_dao(monkeypatch):
    calls = {}

    async def fake_resolve_slugs(session, tag_slugs):
        calls["tag_slugs"] = tag_slugs
        return [[101]]

    async def fake_get_filtered(session, **kwargs):
        calls["filtered"] = kwargs
        return []

    monkeypatch.setattr(ProductReadService, "resolve_slugs_to_grouped_ids", fake_resolve_slugs)
    monkeypatch.setattr(ProductDAO, "get_filtered", fake_get_filtered)

    items = await ProductReadService.get_curated(
        object(),
        area=15,
        area_min=15,
        area_max=24,
        is_inverter=False,
        tag_slugs=["cat-household"],
        limit=12,
    )

    assert items == []
    assert calls["tag_slugs"] == ["cat-household"]
    assert calls["filtered"]["area_min"] == 15
    assert calls["filtered"]["area_max"] == 24
    assert calls["filtered"]["is_inverter"] is False
    assert calls["filtered"]["faceted_tag_ids"] == [[101]]
    assert calls["filtered"]["limit"] == 12


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
