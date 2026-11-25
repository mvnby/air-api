from schemas_tender_search import TenderPlace, TenderSearchProfile
from services.tender_profile_preview import preview_tender_profile
from services.belzakupki_import_service import BelzakupkiImportService


def row(order_id, title, *, work="", address=None, buyer_address=None):
    return order_id, {"belzakupki": {
        "tender": {"title": title, "location": buyer_address},
        "enrichment": {"work_summary": work, "objects": [{"address": address}] if address else []},
    }}


def test_preview_uses_reviewed_execution_site_and_applies_local_exclusions():
    profile = TenderSearchProfile(
        name="Витебская область", included_places=[TenderPlace(region="2")],
        excluded_places=[TenderPlace(region="2", locality="Лепель")],
        included_directions=["air_conditioning"],
    )
    result = preview_tender_profile([
        row(661, "Обслуживание кондиционеров", address="г. Витебск, ул. Гоголя, 8"),
        row(699, "Монтаж кондиционера", address="Витебская область, г. Лепель, пл. Свободы, 1"),
        row(657, "Обслуживание кондиционеров", buyer_address="г. Витебск"),
    ], profile)
    assert {item.order_id: item.result.reason for item in result.items} == {
        661: "eligible", 699: "excluded_place", 657: "unconfirmed_place",
    }


def test_preview_does_not_combine_unlinked_actions_or_separate_lots():
    profile = TenderSearchProfile(name="Закупка с монтажом", mode="strict",
                                  activity_combinations=[["supply", "installation"]])
    results = preview_tender_profile([
        row(658, "Закупка сплит-систем"),
        row(1, "Лот 1: Поставка кондиционеров; лот 2: Монтаж кондиционеров"),
        row(2, "Закупка сплит-систем", work="Поставка кондиционеров; монтаж кондиционеров."),
        row(3, "Поставка кондиционеров с монтажом", work="Поставка кондиционеров с монтажом"),
    ], profile)
    assert [item.result.state for item in results.items] == ["review", "review", "review", "match"]


def test_saved_native_lots_keep_exclusions_and_execution_places_independent():
    native = {
        "source": "goszakupki_by", "external_id": "snapshot", "title": "Разные работы",
        "lot_inventory_complete": True, "lots": [
            {"number": "1", "name": "Техническое обслуживание кондиционеров",
             "delivery_place": "Витебская область, г. Витебск", "unrelated_field": "ignore"},
            {"number": "2", "name": "Монтаж вентиляции", "delivery_place": "Витебская область, г. Лепель"},
        ],
    }
    stored = BelzakupkiImportService._match_snapshot({"id": 42, "profile": {}, "tender": native})["tender"]
    assert stored["lot_inventory_complete"] and "unrelated_field" not in stored["lots"][0]
    profile = TenderSearchProfile(name="Обслуживание в Витебске",
                                  included_places=[TenderPlace(region="2", locality="Витебск")],
                                  activity_combinations=[["maintenance"]])
    preview = preview_tender_profile([(5, {"belzakupki": {"tender": stored}})], profile)
    (item,) = preview.items
    assert item.result.state == "match" and item.result.lot_key == "1"
    assert [(lot.lot_key, lot.reason) for lot in item.lots] == [("1", "eligible"), ("2", "different_place")]
