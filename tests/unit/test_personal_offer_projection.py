from datetime import datetime, timedelta, timezone
import logging

import pytest
from pydantic import ValidationError

from api_contracts.personal_offers import PersonalOfferRoomInput
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
