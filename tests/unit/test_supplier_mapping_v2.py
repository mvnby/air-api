import pytest

from models.supplier import Supplier
from services.supplier_mapping_service import SupplierCatalogService
from services.supplier_match_service import build_offer_match_profile, normalize_offer_title_for_search
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
