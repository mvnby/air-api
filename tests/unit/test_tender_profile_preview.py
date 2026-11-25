from schemas_tender_search import TenderPlace, TenderSearchProfile
from services.tender_profile_preview import preview_tender_profile


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
