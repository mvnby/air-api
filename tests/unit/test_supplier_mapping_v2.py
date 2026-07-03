import pytest

from models.product import Product
from models.supplier import Supplier, SupplierOffer, SupplierPriceSource
from services.supplier_mapping_service import SupplierCatalogService
from services.supplier_match_service import (
    _product_catalog_category,
    _score_candidate,
    build_offer_match_profile,
    normalize_offer_title_for_search,
    suggest_products_for_offer,
)
from services.supplier_source_url import extract_first_source_url, normalize_source_url


def test_normalize_offer_title_for_search_strips_parasites():
    raw = "Сплит-система Внутренний блок MDSA-12HRFN8"
    normalized = normalize_offer_title_for_search(raw)
    assert "сплит" not in normalized
    assert "внутренний блок" not in normalized
    assert "mdsa-12hrfn8" in normalized


def test_extract_first_source_url_from_supplier_row():
    row = ["MDV", "MDSAG-09HRFN8", "https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8)."]

    assert normalize_source_url(row[2]) == "https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8"
    assert extract_first_source_url(row) == "https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8"


@pytest.mark.parametrize(
    ("raw", "expected_tokens", "expected_indoor", "expected_outdoor"),
    [
        (
            "MDV Integra Pro внутренний MDSAG-09HRFN8 / наружный MDOAG-09HFN8",
            ["MDSAG-09HRFN8", "MDOAG-09HFN8"],
            ["MDSAG-09HRFN8"],
            ["MDOAG-09HFN8"],
        ),
        (
            "TCL TAC-09CHSD/XA71IN BreezeIN",
            ["TAC-09CHSD/XA71IN", "TAC-09CHSD", "XA71IN"],
            [],
            [],
        ),
        (
            "Haier Flexis внутренний AS25S2SF3FA-W наружный 1U25S2SM3FA",
            ["AS25S2SF3FA-W", "1U25S2SM3FA"],
            ["AS25S2SF3FA-W"],
            ["1U25S2SM3FA"],
        ),
        (
            "Внутренний блок MDCA5-12HRN1 + Наружный блок MDOU3-12HN1(-L)+Панель T-MBQ4-03E",
            ["MDCA5-12HRN1", "MDOU3-12HN1", "MDOU3-12HN1-L", "T-MBQ4-03E"],
            ["MDCA5-12HRN1"],
            ["MDOU3-12HN1", "MDOU3-12HN1-L"],
        ),
    ],
)
def test_build_offer_match_profile_extracts_model_tokens(raw, expected_tokens, expected_indoor, expected_outdoor):
    profile = build_offer_match_profile(raw)

    for token in expected_tokens:
        assert token in profile.model_tokens
    for token in expected_indoor:
        assert token in profile.indoor_model_tokens
    for token in expected_outdoor:
        assert token in profile.outdoor_model_tokens


def test_product_catalog_category_keeps_multi_component_blocks_after_sanitized_specs():
    assert (
        _product_catalog_category(
            {
                "title": "Внутренний кассетный блок MDV MDCAC4I-12HRFN8",
                "specs": {"type": "внутренний блок", "indoor_type": "кассетный"},
            }
        )
        == "multi"
    )
    assert (
        _product_catalog_category(
            {
                "title": "Наружный блок MDV MD2O-18HFN8",
                "specs": {"type": "наружный блок"},
            }
        )
        == "multi"
    )
    assert (
        _product_catalog_category(
            {
                "title": "MDV Инверторные кассетные сплит-системы MDCAC4I-12HRFN8/MDOU3-12HN1-L",
                "specs": {"type": "полупромышленный кондиционер", "indoor_type": "кассетный"},
            }
        )
        == "semi"
    )


def test_mdv_rac_component_score_prefers_multi_block_over_semi_shape():
    offer_profile = build_offer_match_profile("Внутренний блок MDCAC4I-12HRFN8")

    multi_candidate = _score_candidate(
        offer_profile=offer_profile,
        product={
            "id": 1,
            "title": "Внутренний кассетный блок MDV MDCAC4I MDCAC4I-12HRFN8",
            "price": 1000,
            "specs": {
                "type": "внутренний блок",
                "indoor_type": "кассетный",
                "model_indoor": "MDCAC4I-12HRFN8",
            },
        },
        offer_catalog_categories={"multi"},
        offer_rrc=1000,
    )
    semi_candidate = _score_candidate(
        offer_profile=offer_profile,
        product={
            "id": 2,
            "title": "MDV Инверторные кассетные сплит-системы MDCAC4I-12HRFN8/MDOU3-12HN1-L",
            "price": 1000,
            "specs": {
                "type": "полупромышленный кондиционер",
                "indoor_type": "кассетный",
                "model_indoor": "MDCAC4I-12HRFN8",
                "model_outdoor": "MDOU3-12HN1-L",
            },
        },
        offer_catalog_categories={"multi"},
        offer_rrc=1000,
    )

    assert multi_candidate["score_breakdown"]["catalog_context"] == 18
    assert semi_candidate["score_breakdown"]["catalog_mismatch"] == -34
    assert multi_candidate["score"] - semi_candidate["score"] >= 50


@pytest.mark.asyncio
async def test_supplier_code_auto_generation_unique(db):
    first = await SupplierCatalogService.create_supplier(
        db,
        {
            "name": "Биоконд",
            "is_active": True,
            "priority": 100,
            "spreadsheet_id_or_url": "sheet-one",
        },
    )
    second = await SupplierCatalogService.create_supplier(
        db,
        {
            "name": "Биоконд",
            "is_active": True,
            "priority": 100,
            "spreadsheet_id_or_url": "sheet-two",
        },
    )
    assert first.code != second.code
    assert second.code.startswith(first.code)


@pytest.mark.asyncio
async def test_create_source_rejects_unknown_sheet_name(db, monkeypatch):
    supplier = Supplier(name="S", code="s", priority=1, spreadsheet_id="sheet-1")
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    class FakeGoogleService:
        def list_sheet_tabs(self, spreadsheet_id: str):
            return [{"title": "Prices", "index": 0, "sheet_id": 1}]

        def extract_spreadsheet_id(self, value: str) -> str:
            return value

    from services import supplier_mapping_service

    monkeypatch.setattr(supplier_mapping_service, "get_google_service", lambda: FakeGoogleService())

    with pytest.raises(ValueError):
        await SupplierCatalogService.create_source(
            db,
            {
                "supplier_id": supplier.id,
                "sheet_name": "Unknown",
                "range_a1": "A:E",
                "city_bucket": "minsk",
                "col_external_id": "A",
                "col_title": "B",
                "col_wholesale": "C",
                "col_wholesale_currency": "USD",
                "col_rrc_byn": "D",
                "col_qty": "E",
                "is_active": True,
            },
        )


@pytest.mark.asyncio
async def test_mdv_rac_context_prefers_household_system_over_multi_component(db):
    supplier = Supplier(name="Биоконд", code="biokond", priority=1)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    source = SupplierPriceSource(
        supplier_id=supplier.id,
        sheet_name="MDV RAC",
        col_title="C",
        col_wholesale="F",
        col_wholesale_currency="USD",
        col_rrc_byn="G",
        col_qty="H",
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    household = Product(
        title="MDV iERA inverter MDSAJ-09HRFN8/MDOAJ-09HFN8",
        slug="mdv-iera-household-09",
        price=1350,
        specs={
            "__mdv_catalog": "household",
            "type": "сплит-система",
            "indoor_type": "настенный",
            "model_indoor": "MDSAJ-09HRFN8",
            "model_outdoor": "MDOAJ-09HFN8",
        },
    )
    multi_indoor = Product(
        title="Внутренний блок MDV iERA inverter MDSAJ-09HRFN8",
        slug="mdv-iera-multi-indoor-09",
        price=800,
        specs={
            "__mdv_catalog": "multi",
            "type": "внутренний блок",
            "indoor_type": "настенный",
            "model_indoor": "MDSAJ-09HRFN8",
        },
    )
    db.add_all([household, multi_indoor])
    await db.commit()
    await db.refresh(household)
    await db.refresh(multi_indoor)

    offer = SupplierOffer(
        supplier_id=supplier.id,
        source_id=source.id,
        external_id="MDSAJ-09HRFN8",
        title_raw="Сплит-система MDSAJ-09HRFN8",
        title_normalized="сплит-система mdsaj-09hrfn8",
        model_tokens=["MDSAJ-09HRFN8"],
        indoor_model_tokens=["MDSAJ-09HRFN8"],
        rrc_byn=1350,
        is_active=True,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)

    result = await suggest_products_for_offer(
        db,
        title_raw=offer.title_raw,
        offer=offer,
        limit=5,
    )

    assert result["auto_eligible"] is True
    assert result["candidates"][0]["product_id"] == household.id
    assert result["candidates"][0]["score_breakdown"]["catalog_context"] == 18
    multi_candidate = next(item for item in result["candidates"] if item["product_id"] == multi_indoor.id)
    assert multi_candidate["score_breakdown"]["catalog_mismatch"] == -34


@pytest.mark.asyncio
async def test_mdv_rac_component_context_prefers_multi_component_over_semi_shape(db):
    supplier = Supplier(name="Биоконд", code="biokond", priority=1)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    source = SupplierPriceSource(
        supplier_id=supplier.id,
        sheet_name="MDV RAC",
        col_title="C",
        col_wholesale="F",
        col_wholesale_currency="USD",
        col_rrc_byn="G",
        col_qty="H",
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    multi_indoor = Product(
        title="Внутренний кассетный блок MDV MDCAC4I MDCAC4I-12HRFN8",
        slug="mdv-multi-cassette-indoor-12",
        price=1000,
        specs={
            "__mdv_catalog": "multi",
            "type": "внутренний блок",
            "indoor_type": "кассетный",
            "model_indoor": "MDCAC4I-12HRFN8",
        },
    )
    semi_system = Product(
        title="MDV Инверторные кассетные сплит-системы MDCAC4I-12HRFN8/MDOU3-12HN1-L",
        slug="mdv-semi-cassette-system-12",
        price=1000,
        specs={
            "type": "полупромышленный кондиционер",
            "indoor_type": "кассетный",
            "model_indoor": "MDCAC4I-12HRFN8",
            "model_outdoor": "MDOU3-12HN1-L",
        },
    )
    db.add_all([multi_indoor, semi_system])
    await db.commit()
    await db.refresh(multi_indoor)
    await db.refresh(semi_system)

    offer = SupplierOffer(
        supplier_id=supplier.id,
        source_id=source.id,
        external_id="MDCAC4I-12HRFN8",
        title_raw="Внутренний блок MDCAC4I-12HRFN8",
        title_normalized="внутренний блок mdcac4i-12hrfn8",
        model_tokens=["MDCAC4I-12HRFN8"],
        indoor_model_tokens=["MDCAC4I-12HRFN8"],
        rrc_byn=1000,
        is_active=True,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)

    result = await suggest_products_for_offer(
        db,
        title_raw=offer.title_raw,
        offer=offer,
        limit=5,
    )

    assert result["auto_eligible"] is True
    assert result["candidates"][0]["product_id"] == multi_indoor.id
    assert result["candidates"][0]["score_breakdown"]["catalog_context"] == 18
    semi_candidate = next(item for item in result["candidates"] if item["product_id"] == semi_system.id)
    assert semi_candidate["score_breakdown"]["catalog_mismatch"] == -34
