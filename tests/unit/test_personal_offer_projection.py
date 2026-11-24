from datetime import datetime, timedelta, timezone
import logging

import pytest
from pydantic import ValidationError

from api_contracts.personal_offers import PersonalOfferDraftInput, PersonalOfferRoomInput, PublicPersonalOfferResponse
from core.app_observability import _PersonalOfferAccessLogFilter, _scrub_sentry_event
from models import Product
from services.personal_offer_projection import PersonalOfferProjection, display_room_title
from services.public_catalog_disclosure import CANONICAL_PUBLIC_DISCLOSURE
from services.public_catalog_visibility_service import PublicProductProjection


def test_personal_offer_projection_uses_exact_by_room_prices_and_confirmed_specs():
    product = Product(
        id=1, title="Sample model", slug="sample-model", price=1570,
        main_image="javascript:alert(1)", specs={"noise_indoor": "20/25/30 dB", "wifi_ready": "ready"},
    )
    product_map = {1: PublicProductProjection(product, 1570, None, CANONICAL_PUBLIC_DISCLOSURE)}
    option = {"product_id": 1, "price_byn": "1520.10", "note": "  Что входит  "}
    rooms = [
        PersonalOfferRoomInput(title="  Зал  ", installation={
            "mode": "fixed", "price_byn": "500.25", "description": "Монтаж",
        }, options=[option]),
        PersonalOfferRoomInput(title="  ", installation={"mode": "unknown"}, options=[option]),
    ]
    projection = PersonalOfferProjection.build(
        rooms, datetime.now(timezone.utc) + timedelta(days=7), product_map,
    ).model_dump(mode="json")
    assert [room["title"] for room in projection["rooms"]] == ["Зал", "Помещение 2"]
    assert projection["rooms"][0]["options"][0] == {
        "title": "Sample model", "slug": "sample-model", "main_image": None,
        "price_byn": "1520.10", "original_price_byn": "1570", "total_price_byn": "2020.35",
        "note": "Что входит", "cooling_power_kw": None, "noise_indoor_min_db": 20.0,
        "is_inverter": None, "wifi": "ready",
    }
    assert projection["rooms"][1]["options"][0]["total_price_byn"] is None


def test_empty_titles_use_current_position_and_single_room_fallback():
    assert display_room_title(None, 1, 1) == "Подбор кондиционера"
    assert display_room_title("  ", 3, 3) == "Помещение 3"
    assert display_room_title("  Склад  ", 1, 1) == "Склад"


def test_legacy_snapshot_defaults_to_choice_without_a_total():
    projection = PublicPersonalOfferResponse.model_validate({
        "expires_at": "2035-01-01T00:00:00Z",
        "rooms": [{"title": "Зал", "installation": {"mode": "none", "price_byn": None, "description": None}, "options": []}],
    })
    room = projection.rooms[0]
    assert room.selection_mode == "choice"
    assert room.equipment_total_byn is None
    assert room.total_with_installation_byn is None


def test_alternatives_cannot_have_a_total_and_offer_modes_cannot_be_mixed():
    room = {"installation": {"mode": "none"}, "options": [{"product_id": 1, "price_byn": "1520.10"}]}
    with pytest.raises(ValidationError, match="Итог можно показать только для комплекта"):
        PersonalOfferRoomInput.model_validate({**room, "show_total": True})
    with pytest.raises(ValidationError, match="Выберите один режим для всего предложения"):
        PersonalOfferDraftInput.model_validate({
            "expires_at": "2035-01-01T00:00:00Z",
            "rooms": [room, {**room, "selection_mode": "package"}],
        })


@pytest.mark.parametrize(("mode", "show_total", "equipment", "with_installation"), [
    ("none", True, "3040.30", None),
    ("unknown", True, "3040.30", None),
    ("fixed", True, "3040.30", "3540.55"),
    ("fixed", False, None, None),
])
def test_package_adds_equipment_and_installation_once(mode, show_total, equipment, with_installation):
    product = Product(id=1, title="Sample model", slug="sample-model", price=1570)
    products = {1: PublicProductProjection(product, 1570, None, CANONICAL_PUBLIC_DISCLOSURE)}
    room = PersonalOfferRoomInput.model_validate({
        "selection_mode": "package",
        "show_total": show_total,
        "installation": {"mode": mode, "price_byn": "500.25" if mode == "fixed" else None},
        "options": [
            {"product_id": 1, "price_byn": "1520.10", "note": "Гостиная"},
            {"product_id": 1, "price_byn": "1520.20", "note": "Спальня"},
        ],
    })
    snapshot = PersonalOfferProjection.build(
        [room], datetime.now(timezone.utc) + timedelta(days=7), products,
    ).model_dump(mode="json")["rooms"][0]
    assert snapshot["title"] == "Комплект оборудования"
    assert snapshot["selection_mode"] == "package"
    assert snapshot["equipment_total_byn"] == equipment
    assert snapshot["total_with_installation_byn"] == with_installation
    assert [(item["note"], item["total_price_byn"]) for item in snapshot["options"]] == [
        ("Гостиная", None), ("Спальня", None),
    ]


@pytest.mark.parametrize("installation", [
    {"mode": "fixed"}, {"mode": "none", "price_byn": "0"}, {"mode": "fixed", "price_byn": "0.001"},
])
def test_fixed_installation_requires_exact_money_and_other_modes_cannot_sell_installation(installation):
    with pytest.raises(ValidationError):
        PersonalOfferRoomInput(installation=installation, options=[{"product_id": 1, "price_byn": "5.21"}])


def test_application_access_logs_and_sentry_scrub_bearer_link_path():
    token = "x" * 43
    target = f"/api/v1/personal-offers/{token}?campaign=foo"
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, "%s %s %s %s %s",
        ("host", "GET", target, "HTTP/1.1", 200), None,
    )
    assert _PersonalOfferAccessLogFilter().filter(record)
    assert record.args[2] == "/api/v1/personal-offers/[redacted]?campaign=foo"
    scrubbed = _scrub_sentry_event({
        "request": {"url": f"https://mvn.by/predlozhenie/{token}/"}, "transaction": target,
    }, {})
    assert token not in str(scrubbed)
