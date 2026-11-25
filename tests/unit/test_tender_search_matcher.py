from schemas_tender_search import TenderLotSignals, TenderPlace, TenderSearchProfile
from services.tender_search_matcher import match_tender_lot


def test_excluded_district_and_mixed_equipment_are_evaluated_per_lot():
    profile = TenderSearchProfile(
        name="Витебская область",
        included_places=[TenderPlace(region="2")],
        excluded_places=[TenderPlace(region="2", locality="Лепель")],
        excluded_directions=["ventilation", "refrigeration"],
    )
    ac = TenderLotSignals(
        lot_key="AC", execution_places=[TenderPlace(region="2", locality="г. Витебск, ул. Гоголя")],
        confirmed_directions={"air_conditioning"}, directions_complete=True, places_complete=True,
    )
    assert match_tender_lot(profile, ac).state == "match"
    lepel = ac.model_copy(update={"execution_places": [TenderPlace(region="2", locality="г. Лепель, пл. Свободы")],
                                "required_activities": {"installation"}})
    assert match_tender_lot(profile, lepel).reason == "excluded_place"
    ventilation = ac.model_copy(update={"lot_key": "vent", "confirmed_directions": {"ventilation"}})
    assert match_tender_lot(profile, ventilation).reason == "excluded_direction"
    mixed = ac.model_copy(update={"confirmed_directions": {"air_conditioning", "ventilation"}})
    assert match_tender_lot(profile, mixed).state == "excluded"


def test_strict_supply_and_installation_need_evidence_in_the_same_lot():
    profile = TenderSearchProfile(name="Поставка с монтажом", mode="strict",
                                  activity_combinations=[["supply", "installation"]])
    supply = TenderLotSignals(
        lot_key="equipment", confirmed_directions={"air_conditioning"}, directions_complete=True,
        required_activities={"supply"},
    )
    assert match_tender_lot(profile, supply).state == "review"
    assert match_tender_lot(profile, supply.model_copy(update={"activities_complete": True})).state == "excluded"
    separate_installation = supply.model_copy(update={"lot_key": "services", "required_activities": {"installation"},
                                                       "activities_complete": True})
    assert match_tender_lot(profile, separate_installation).state == "excluded"
    combined = supply.model_copy(update={"required_activities": {"supply", "installation"}, "activities_complete": True})
    assert match_tender_lot(profile, combined).state == "match"


def test_wide_and_strict_modes_use_different_completeness_thresholds():
    broad = TenderSearchProfile(name="Холодильное оборудование", included_directions=["refrigeration"])
    typed_lot = TenderLotSignals(lot_key="fridges", confirmed_directions={"refrigeration"})
    assert match_tender_lot(broad, typed_lot).state == "match"
    assert match_tender_lot(broad.model_copy(update={"mode": "strict"}), typed_lot).state == "review"
    location_needed = broad.model_copy(update={"included_places": [TenderPlace(region="5")]})
    assert match_tender_lot(location_needed, typed_lot).reason == "unconfirmed_place"
    minsk_region = typed_lot.model_copy(update={"execution_places": [TenderPlace(region="6")], "places_complete": True})
    assert match_tender_lot(location_needed, minsk_region).reason == "different_place"
