from decimal import Decimal
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from models import InstallationPriceBook
from models.tenancy import TenantScope
from schemas_installation_price_book import (
    InstallationMatcher, InstallationPreviewPayload, InstallationPreviewResponse, InstallationResolveResponse,
    InstallationTarget, TypedInstallationProfile,
)
from services.installation_price_book_service import InstallationPriceBookService as BookService
from services.installation_preview_receipt_service import InstallationPreviewReceiptService


def _mock_receipts(monkeypatch):
    saved = []
    async def replay(_session, _scope, **_kwargs):
        return None
    async def store(_session, _scope, **kwargs):
        saved.append(kwargs)
        response = kwargs["snapshot"]["result"].copy()
        response["preview_ref"] = "test-preview-ref"
        response["expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=30)
        return InstallationPreviewResponse.model_validate(response)
    monkeypatch.setattr(InstallationPreviewReceiptService, "replay", replay)
    monkeypatch.setattr(InstallationPreviewReceiptService, "store_or_replay", store)
    return saved


def _entry(code="installation.wall", indoor_type="wall", *, mode="fixed", weight=False):
    match = InstallationMatcher(
        indoor_type=indoor_type, capacity_min_kw=Decimal("2"), capacity_max_kw=Decimal("4"),
        pipe_liquid='1/4"', pipe_gas='3/8"',
        weight_source="weight_outdoor" if weight else None,
        weight_min_kg=Decimal("20") if weight else None,
    )
    def rule(rule_id, component_code, kind, price, optional=False):
        return {"id": rule_id, "code": component_code, "rule_type": kind, "name": component_code,
                "line_template": "{name}", "unit": "шт" if kind != "per_meter_over_included" else "м",
                "unit_price": str(price), "is_optional": optional, "sort_order": rule_id}
    return {"tariff_id": 1, "code": code, "match": match.model_dump(mode="json"),
            "mode": mode, "base_price": "500.00", "short_name": "Монтаж",
            "description": "Монтаж с трассой", "included_route_m": "3",
            "included_holes": {"diamond": "1"},
            "rules": [
                rule(1, "route.extra_m", "per_meter_over_included", "10.25"),
                rule(2, "hole.diamond.extra", "per_hole_manual", "50.00"),
                rule(3, "pump.supply", "per_unit_manual", "80.00", True),
                rule(4, "pump.install", "per_unit_manual", "20.00", True),
                rule(5, "access.lift", "fixed_once", "100.00", True),
            ]}


def test_publish_blocks_equal_specificity_overlap_and_incomplete_fixed_matcher():
    first = _entry()
    second = _entry("installation.wall.other")
    with pytest.raises(HTTPException) as error:
        BookService._validate_entries([first, second])
    assert error.value.detail["code"] == "matcher_conflict"
    missing_pair = _entry()
    missing_pair["match"]["pipe_liquid"] = None
    missing_pair["match"]["pipe_gas"] = None
    with pytest.raises(HTTPException) as error:
        BookService._validate_entries([missing_pair])
    assert error.value.detail["code"] == "incomplete_fixed_matcher"


@pytest.mark.parametrize("code,field,value", [
    ("pump.install", "rule_type", "per_hole_manual"),
    ("pump.supply", "unit", "м"),
    ("access.lift", "is_optional", False),
    ("chase.extra_m", "rule_type", "fixed_once"),
    ("route.extra_m", "is_optional", True),
    ("hole.diamond.extra", "unit", "м"),
    ("discount.equipment_bundle", "is_optional", True),
])
def test_publication_rejects_wrong_component_semantics(code, field, value):
    entry = _entry()
    if code not in {rule["code"] for rule in entry["rules"]}:
        entry["rules"].append({"id": 6, "code": code, "rule_type": "fixed_once",
                               "unit": "шт", "unit_price": "10.00", "is_optional": False})
    next(rule for rule in entry["rules"] if rule["code"] == code)[field] = value
    with pytest.raises(HTTPException) as error:
        BookService._validate_entries([entry])
    assert error.value.detail["code"] == "invalid_component_rule"


def test_preview_requires_actual_route_and_holes():
    for omitted in ("route_length_m", "holes_by_type"):
        installation = {"key": "one", "typed_profile": {"product_kind": "complete_split_system",
                        "indoor_type": "wall", "confirmed": True},
                        "route_length_m": 3, "holes_by_type": {}}
        installation.pop(omitted)
        with pytest.raises(ValidationError):
            InstallationPreviewPayload.model_validate({"installations": [installation]})


@pytest.mark.parametrize("other_type", ["cassette", "duct", "floor_ceiling", "column", "console"])
def test_matcher_separates_types_capacity_pipe_and_conditional_weight(other_type):
    wall = _entry()
    profile = TypedInstallationProfile(product_kind="complete_split_system", indoor_type="wall",
        capacity_cooling_kw=Decimal("2"), pipe_liquid="6.35 mm", pipe_gas='3/8"', confirmed=True)
    assert BookService._match(profile, wall) == (True, None)
    assert BookService._match(profile, _entry(f"installation.{other_type}", other_type)) == (False, None)
    assert BookService._match(profile.model_copy(update={"capacity_cooling_kw": Decimal("4.1")}), wall) == (False, None)
    assert BookService._match(profile.model_copy(update={"pipe_gas": '1/2"'}), wall) == (False, None)
    assert BookService._match(profile.model_copy(update={"capacity_cooling_kw": None}), wall) == (False, "missing_cooling_capacity")
    assert BookService._match(profile, _entry(weight=True)) == (False, "missing_required_weight")
    assert BookService._match(profile.model_copy(update={"weight_outdoor": Decimal("25")}), _entry(weight=True)) == (True, None)


@pytest.mark.asyncio
async def test_resolve_quotes_unknown_and_never_falls_back_to_wall(monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=3)
    book = InstallationPriceBook(id=8, tenant_id=1, revision=2, fingerprint="x", entries=[_entry()])
    async def profile(_session, _scope, target):
        return target.typed_profile, {"indoor_type": "confirmed_manual"}
    monkeypatch.setattr(BookService, "_profile", profile)
    cassette = InstallationTarget(typed_profile=TypedInstallationProfile(
        product_kind="complete_split_system", indoor_type="cassette", confirmed=True,
        capacity_cooling_kw=3, pipe_liquid='1/4"', pipe_gas='3/8"'))
    result, entry = await BookService.resolve(None, scope, cassette, book=book)
    assert result.status == "quote" and result.reason_code == "no_matching_tariff"
    assert entry is None and result.base_price is None
    block = InstallationTarget(typed_profile=TypedInstallationProfile(product_kind="indoor_unit", indoor_type="wall", confirmed=True))
    result, entry = await BookService.resolve(None, scope, block, book=book)
    assert result.status == "unavailable" and entry is None
    incomplete = InstallationTarget(typed_profile=TypedInstallationProfile(
        product_kind="complete_split_system", indoor_type="wall", confirmed=True,
        pipe_liquid='1/4"', pipe_gas='3/8"'))
    result, entry = await BookService.resolve(None, scope, incomplete, book=book)
    assert result.status == "quote" and result.reason_code == "missing_cooling_capacity"
    assert result.base_price is None and entry is None


@pytest.mark.asyncio
async def test_resolve_missing_weight_blocks_only_more_specific_compatible_tariff(monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=3)
    generic = _entry(code="installation.wall.generic")
    heavy = _entry(code="installation.wall.heavy", weight=True)
    heavy["base_price"] = "700.00"
    irrelevant = _entry(code="installation.cassette.heavy", indoor_type="cassette", weight=True)
    BookService._validate_entries([generic, heavy, irrelevant])
    book = InstallationPriceBook(id=8, tenant_id=1, revision=1, fingerprint="x",
                                 entries=[generic, heavy, irrelevant])
    async def profile(_session, _scope, target):
        return target.typed_profile, {}
    monkeypatch.setattr(BookService, "_profile", profile)
    base = dict(product_kind="complete_split_system", indoor_type="wall", confirmed=True,
                capacity_cooling_kw=3, pipe_liquid='1/4"', pipe_gas='3/8"')
    target = InstallationTarget(typed_profile=TypedInstallationProfile(**base))
    result, entry = await BookService.resolve(None, scope, target, book=book)
    assert result.status == "quote" and result.reason_code == "missing_required_weight" and entry is None
    for weight, expected_code, expected_price in ((10, generic["code"], 500),
                                                  (25, heavy["code"], 700)):
        target = InstallationTarget(typed_profile=TypedInstallationProfile(**base, weight_outdoor=weight))
        result, entry = await BookService.resolve(None, scope, target, book=book)
        assert result.status == "fixed" and result.tariff_code == expected_code
        assert result.base_price == expected_price and entry is not None
    without_heavy = InstallationPriceBook(id=9, tenant_id=1, revision=1, fingerprint="y",
                                          entries=[generic, irrelevant])
    result, _ = await BookService.resolve(None, scope, InstallationTarget(
        typed_profile=TypedInstallationProfile(**base)), book=without_heavy)
    assert result.status == "fixed" and result.tariff_code == generic["code"]


@pytest.mark.asyncio
async def test_preview_uses_included_overages_explicit_extras_and_one_site_lift(monkeypatch):
    saved = _mock_receipts(monkeypatch)
    scope = TenantScope(tenant_id=12, storefront_id=34)
    entry = _entry()
    book = InstallationPriceBook(id=8, tenant_id=12, revision=2, fingerprint="x", entries=[entry])
    async def latest(_session, _scope):
        return book
    async def resolve(_session, _scope, _target, *, book=None):
        return InstallationResolveResponse(status="fixed", scope_ref="scope"), entry
    monkeypatch.setattr(BookService, "latest", latest)
    monkeypatch.setattr(BookService, "resolve", resolve)
    payload = InstallationPreviewPayload.model_validate({
        "installations": [
            {"key": "A", "typed_profile": {"product_kind": "complete_split_system", "indoor_type": "wall", "confirmed": True},
             "route_length_m": "6.5", "holes_by_type": {"diamond": 2}, "extras": [{"code": "pump.install"}]},
            {"key": "B", "typed_profile": {"product_kind": "complete_split_system", "indoor_type": "wall", "confirmed": True},
             "route_length_m": "3", "holes_by_type": {"diamond": 1}},
        ],
        "site_extras": [{"code": "access.lift"}], "expected_revision": 2,
    })
    result = await BookService.preview(None, scope, payload, idempotency_key="installation-preview-one")
    assert result.status == "fixed"
    assert result.total == Decimal("1205.88")
    assert [part.code for part in result.components].count("access.lift") == 1
    assert "pump.supply" not in [part.code for part in result.components]
    route = next(part for part in result.components if part.code == "route.extra_m")
    assert (route.actual, route.included, route.quantity, route.gross) == (
        Decimal("6.5"), Decimal("3"), Decimal("3.5"), Decimal("35.88"))
    hole = next(part for part in result.components if part.code == "hole.diamond.extra")
    assert (hole.actual, hole.included, hole.quantity) == (Decimal("2"), Decimal("1"), Decimal("1"))
    assert saved[0]["snapshot"]["revision"] == 2
    assert saved[0]["snapshot"]["scope"] == {"tenant_id": 12, "storefront_id": 34}
    assert result.installations[0].measured[0].actual == Decimal("6.5")
    assert result.installations[0].measured[0].extra == Decimal("3.5")
    assert result.installations[1].measured[0].extra == 0
    assert [item.code for item in result.installations[0].selected_extras] == ["pump.install"]
    assert [item.code for item in result.site_work] == ["access.lift"]
    assert "установка b" in result.customer_text.lower()
    assert "насоса" in result.customer_text.lower()
    assert "поставка насоса" not in result.customer_text.lower()
    assert result.customer_text.count("На объекте:") == 1
    with pytest.raises(HTTPException) as error:
        await BookService.preview(None, scope, payload.model_copy(update={"expected_revision": 1}), idempotency_key="installation-preview-two")
    assert error.value.status_code == 409 and error.value.detail["code"] == "price_changed"
    original_component = BookService._rule_component.__func__
    def omit_selected_pump(cls, entry, rule, key, **kwargs):
        if rule["code"] == "pump.install":
            return None
        return original_component(cls, entry, rule, key, **kwargs)
    monkeypatch.setattr(BookService, "_rule_component", classmethod(omit_selected_pump))
    with pytest.raises(HTTPException) as error:
        await BookService.preview(None, scope, payload, idempotency_key="installation-preview-three")
    assert error.value.status_code == 422 and error.value.detail["code"] == "unpriced_component"


@pytest.mark.asyncio
async def test_named_bundle_discount_allocates_cents_without_new_charge(monkeypatch):
    _mock_receipts(monkeypatch)
    scope = TenantScope(tenant_id=12, storefront_id=34)
    entry = _entry()
    entry["rules"].append({"id": 6, "code": "discount.equipment_bundle", "rule_type": "fixed_once",
                           "name": "Скидка комплекта", "line_template": "{name}", "unit": "шт",
                           "unit_price": "10.01", "is_optional": False, "sort_order": 6})
    BookService._validate_entries([entry])
    book = InstallationPriceBook(id=9, tenant_id=12, revision=1, fingerprint="x", entries=[entry])
    async def latest(_session, _scope):
        return book
    async def resolve(_session, _scope, _target, *, book=None):
        return InstallationResolveResponse(status="fixed", scope_ref="scope"), entry
    monkeypatch.setattr(BookService, "latest", latest)
    monkeypatch.setattr(BookService, "resolve", resolve)
    result = await BookService.preview(None, scope, InstallationPreviewPayload.model_validate({
        "installations": [{"key": "A", "product_id": 1, "route_length_m": 4,
                           "holes_by_type": {},
                           "extras": [{"code": "pump.install"}]}]
    }), idempotency_key="discount-preview")
    assert result.subtotal == Decimal("530.25")
    assert result.discount == Decimal("10.01")
    assert result.total == Decimal("520.24")
    assert [(item.code, item.amount) for item in result.applied_discounts] == [
        ("discount.equipment_bundle", Decimal("10.01"))]
    assert sum(item.net for item in result.components) == result.total


@pytest.mark.asyncio
async def test_quote_tariff_never_exposes_zero_as_a_price(monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=3)
    entry = _entry(mode="quote")
    entry["base_price"] = "0.00"
    entry["rules"] = []
    BookService._validate_entries([entry])
    book = InstallationPriceBook(id=8, tenant_id=1, revision=2, fingerprint="x", entries=[entry])
    async def profile(_session, _scope, target):
        return target.typed_profile, {}
    async def latest(_session, _scope):
        return book
    monkeypatch.setattr(BookService, "_profile", profile)
    monkeypatch.setattr(BookService, "latest", latest)
    target = {"product_kind": "complete_split_system", "indoor_type": "wall", "confirmed": True,
              "capacity_cooling_kw": "2.5", "pipe_liquid": '1/4"', "pipe_gas": '3/8"'}
    resolved, _ = await BookService.resolve(None, scope, InstallationTarget(typed_profile=target), book=book)
    assert resolved.status == "quote" and resolved.base_price is None
    _mock_receipts(monkeypatch)
    preview = await BookService.preview(None, scope, InstallationPreviewPayload.model_validate({
        "installations": [{"key": "one", "typed_profile": target, "route_length_m": 3, "holes_by_type": {}}]
    }), idempotency_key="quote-preview-request")
    assert preview.status == "quote" and preview.total is None and preview.preview_ref is None


def test_product_capacity_requires_one_numeric_value_before_compatibility():
    assert BookService._single_quantity("2,5 кВт", kind="power") == Decimal("2.5")
    assert BookService._single_quantity(2.5, kind="power") == Decimal("2.5")
    assert BookService._single_quantity("2.5-3.5 кВт", kind="power") is None
    assert BookService._single_quantity("~2.5 кВт", kind="power") is None
    assert BookService._single_quantity("22 кг", kind="weight") == Decimal("22")
