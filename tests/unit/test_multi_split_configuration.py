from collections import Counter
from datetime import datetime

from api_contracts.multi_split import MultiSplitComponent, MultiSplitPreviewRequest, MultiSplitPreviewResponse
from models import MultiSplitCompatibilityProfile
from services.multi_split_configuration_service import MultiSplitPreviewResult, assess_compatibility


def profile(**overrides):
    values = {
        "outdoor_product_id": 42,
        "verification_status": "verified",
        "source_url": "https://manufacturer.example/matrix.pdf",
        "source_version": "2026-09",
        "version": 2,
        "verified_at": datetime(2026, 9, 27),
        "allowed_indoor_product_ids": [11, 12],
        "exact_combinations": [{"lines": [
            {"indoor_product_id": 11, "quantity": 2},
            {"indoor_product_id": 12, "quantity": 1},
        ]}],
        "max_indoor_units": 3,
    }
    values.update(overrides)
    return MultiSplitCompatibilityProfile(**values)


def test_without_reviewed_source_requires_specialist():
    assert assess_compatibility(None, Counter({11: 2, 12: 1}), 3)[0] == "requires_specialist"
    assert assess_compatibility(profile(verification_status="draft"), Counter({11: 2, 12: 1}), 3)[0] == "requires_specialist"
    assert assess_compatibility(profile(source_url=None), Counter({11: 2, 12: 1}), 3)[0] == "requires_specialist"
    assert assess_compatibility(profile(source_url="javascript:alert(1)"), Counter({11: 2, 12: 1}), 3)[0] == "requires_specialist"
    assert assess_compatibility(profile(exact_combinations=[]), Counter({11: 2, 12: 1}), 3)[0] == "requires_specialist"


def test_exact_reviewed_combination_only():
    confirmed = assess_compatibility(profile(), Counter({11: 2, 12: 1}), 3)
    assert confirmed[0] == "confirmed"
    assert confirmed[2] is True
    assert assess_compatibility(profile(), Counter({11: 1, 12: 1}), 2)[0] == "incompatible"
    assert assess_compatibility(profile(), Counter({11: 2, 12: 1}), 4)[0] == "incompatible"
    assert assess_compatibility(profile(), Counter({11: 2, 13: 1}), 3)[0] == "incompatible"


def test_malformed_reviewed_profile_fails_closed():
    status, _, verified = assess_compatibility(profile(exact_combinations=[{"wrong": []}]), Counter({11: 2}), 2)
    assert status == "requires_specialist"
    assert verified is False


def test_public_projection_has_no_commercial_cost_fields():
    public = MultiSplitPreviewResponse(
        status="requires_specialist",
        explanation="Проверка нужна",
        composition_complete=False,
        equipment_total_byn=2000,
        components=[],
    ).model_dump()
    assert "purchase_cost_total_byn" not in public
    assert "margin_byn" not in public


def test_preview_request_requires_one_room_per_indoor_unit():
    request = MultiSplitPreviewRequest.model_validate({
        "outdoor_product_id": 42,
        "rooms": [
            {"name": "Кухня", "indoor_product_id": 11},
            {"name": "Спальня", "indoor_product_id": 11},
        ],
    })
    assert len(request.rooms) == 2


def test_manager_preview_keeps_purchase_cents_and_demo_hides_cost():
    public = MultiSplitPreviewResponse(
        status="requires_specialist", explanation="Проверка нужна",
        composition_complete=False, equipment_total_byn=1800,
        components=[MultiSplitComponent(
            product_id=11, title="Блок", product_kind="indoor_unit", quantity=2,
            unit_price_byn=900, total_price_byn=1800, availability="in_stock_now",
        )],
    )
    result = MultiSplitPreviewResult(public=public, products={}, metrics={11: {"min_cost_byn": 478.95}}, profile=None)
    assert result.manager_response().purchase_cost_total_byn == 957.9
    assert result.manager_response().margin_byn == 842.1
    assert result.manager_response(show_commercial=False).purchase_cost_total_byn is None
