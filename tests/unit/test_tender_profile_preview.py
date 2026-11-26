import pytest

from schemas_tender_search import TenderPlace, TenderSearchProfile
from services.tender_profile_preview import match_publication, preview_tender_profile
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


@pytest.mark.parametrize("source", ["goszakupki_by", "gias_by"])
def test_saved_native_lots_keep_exclusions_and_execution_places_independent(source):
    native = {
        "source": source, "external_id": "snapshot", "title": "Разные работы",
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


def test_explicit_ventilation_work_and_abbreviated_region_are_not_dropped():
    title = "Выполнение строительно-монтажных работ по устройству вентиляции и изоляции"
    profile = TenderSearchProfile(
        name="Вентиляция в области", included_directions=["ventilation"],
        included_places=[TenderPlace(region="2")], activity_combinations=[["installation"]],
    )
    (found,) = preview_tender_profile([
        row(1, title, address="Витебская обл., аг. Мазолово, ул. Мелиораторов, 7А"),
    ], profile).items
    assert found.result.state == "match"
    (excluded,) = preview_tender_profile([
        row(1, title, address="Витебская обл., аг. Мазолово, ул. Мелиораторов, 7А"),
    ], TenderSearchProfile(name="Без вентиляции", excluded_directions=["ventilation"])).items
    assert excluded.result.reason == "excluded_direction"


def test_required_ventilation_is_excluded_within_the_verified_lot():
    title = "Техническое обслуживание кондиционеров"
    mixed = {
        "number": "1", "name": "Работы по техническому обслуживанию и ремонту систем вентиляции и кондиционирования воздуха",
        "delivery_place": "Республика Беларусь, Гродненская область, г. Гродно, ул. Дубко, 19",
    }
    tender = {"source": "gias_by", "lot_inventory_complete": True, "lots": [mixed]}
    profile = TenderSearchProfile(
        name="Обслуживание и ремонт кондиционеров", mode="strict", included_directions=["air_conditioning"],
        included_places=[TenderPlace(region="4", locality="Гродно")],
        activity_combinations=[["maintenance", "repair"]],
    )
    without_ventilation = profile.model_copy(update={"excluded_directions": ["ventilation"]})
    result, _ = match_publication(title, tender, without_ventilation)
    assert (result.state, result.reason) == ("excluded", "excluded_direction")
    allowed, _ = match_publication(title, tender, profile)
    assert allowed.state == "match"

    separate = {
        "number": "2", "name": "Техническое обслуживание и ремонт кондиционеров",
        "delivery_place": mixed["delivery_place"],
    }
    result, lots = match_publication(title, {**tender, "lots": [mixed, separate]}, without_ventilation)
    assert (result.lot_key, result.state) == ("2", "match")
    assert [(lot.lot_key, lot.reason) for lot in lots] == [("1", "excluded_direction"), ("2", "eligible")]

    unverified, _ = match_publication(title, {**tender, "lot_inventory_complete": False}, without_ventilation)
    assert unverified.state == "review"


def test_native_lot_confirms_supply_and_exhaust_ventilation_repair():
    name = "Текущий ремонт приточно-вытяжной системы вентиляции в помещениях тира"
    tender = {
        "source": "gias_by",
        "lot_inventory_complete": True,
        "lots": [{"number": "1", "name": name}],
    }
    profile = TenderSearchProfile(
        name="Ремонт вентиляции", mode="strict", included_directions=["ventilation"],
        activity_combinations=[["repair"]],
    )
    assert match_publication(name, tender, profile)[0].state == "match"
    excluded = TenderSearchProfile(name="Без вентиляции", excluded_directions=["ventilation"])
    assert match_publication(name, tender, excluded)[0].reason == "excluded_direction"


@pytest.mark.parametrize(("name", "expected"), [
    ("Кондиционеры с установкой в г. Бобруйск", "match"),
    ("Кондиционеры с установкой вентиляции", "review"),
    ("Кондиционеры с установкой при необходимости", "review"),
    ("Кронштейны для кондиционеров с установкой в г. Бобруйск", "review"),
])
def test_native_lot_installation_qualifier_stays_with_the_named_equipment(name, expected):
    tender = {"source": "goszakupki_by", "lot_inventory_complete": True, "lots": [{"number": "1", "name": name}]}
    profile = TenderSearchProfile(
        name="Установка кондиционеров", mode="strict", included_directions=["air_conditioning"],
        activity_combinations=[["installation"]],
    )
    assert match_publication(name, tender, profile)[0].state == expected
    combination = profile.model_copy(update={"activity_combinations": [["supply", "installation"]]})
    assert match_publication(name, tender, combination)[0].state == "review"


def test_conflicting_native_delivery_city_stays_in_review():
    name = "кондиционеры с установкой в г.Бобруйск"
    lot = {
        "number": "1", "name": name,
        "delivery_place": "Республика Беларусь, Могилевская область, 212030, Могилёв, ул.Тимирязевская, д.29",
    }
    tender = {"source": "goszakupki_by", "lot_inventory_complete": True, "lots": [lot]}
    bobruisk = TenderPlace(region="7", locality="Бобруйск")
    selected = TenderSearchProfile(
        name="Установка в Бобруйске", mode="strict", included_places=[bobruisk], activity_combinations=[["installation"]],
    )
    excluded = TenderSearchProfile(name="Кроме Бобруйска", excluded_places=[bobruisk])
    assert match_publication(name, tender, selected)[0].reason == "unconfirmed_place"
    assert match_publication(name, tender, excluded)[0].reason == "unconfirmed_place"

    localized = {**lot, "name": "Кондиционеры с установкой в г. Бобруйске",
                 "delivery_place": "Могилевская область, г. Бобруйск, ул. Минская, 20"}
    assert match_publication(name, {**tender, "lots": [localized]}, selected)[0].state == "match"


@pytest.mark.parametrize(
    ("title", "reason"),
    [
        ("Поставка кондиционеров и монтаж вентиляции", "unconfirmed_activity"),
        ("Поставка кондиционеров, поставка вентиляции с монтажом", "unconfirmed_activity"),
        ("Поставка кондиционеров и систем вентиляции с монтажом", "eligible"),
    ],
)
def test_installation_must_belong_to_the_selected_equipment(title, reason):
    tender = {
        "source": "goszakupki_by", "lot_inventory_complete": True,
        "lots": [{"number": "1", "name": title}],
    }
    profile = TenderSearchProfile(
        name="Кондиционеры с монтажом", mode="strict", included_directions=["air_conditioning"],
        activity_combinations=[["supply", "installation"]],
    )
    result, _ = match_publication(title, tender, profile)
    assert result.reason == reason


@pytest.mark.parametrize(
    ("title", "lot_name"),
    [
        ("Монтаж вентиляции и кондиционеров", "Монтаж кондиционеров"),
        ("Поставка кондиционеров", "Поставка кондиционеров без монтажа вентиляции"),
        ("Ремонт климатического оборудования", "Ремонт вентиляции или кондиционеров"),
        ("Ремонт климатического оборудования", "Ремонт вентиляции/кондиционеров"),
    ],
)
def test_uncertain_or_optional_ventilation_stays_on_review(title, lot_name):
    tender = {
        "source": "gias_by", "lot_inventory_complete": True,
        "lots": [{"number": "1", "name": lot_name}],
    }
    profile = TenderSearchProfile(name="Без вентиляции", excluded_directions=["ventilation"])
    result, _ = match_publication(title, tender, profile)
    assert result.state == "review"
