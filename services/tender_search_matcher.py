"""Per-lot tender matching for company profiles."""

from typing import get_args

from schemas_tender_search import (
    TenderDirection,
    TenderLotMatch,
    TenderLotSignals,
    TenderPlace,
    TenderSearchProfile,
)

_HVAC_DIRECTIONS = set(get_args(TenderDirection))


def _matches_place(rule: TenderPlace, place: TenderPlace) -> bool:
    if rule.region != place.region:
        return False
    return rule.locality is None or f" {rule.locality} " in f" {place.locality or ''} "


def match_tender_lot(profile: TenderSearchProfile, lot: TenderLotSignals) -> TenderLotMatch:
    """Require combinations in one lot and give explicit exclusions precedence."""
    strict = profile.mode == "strict"
    if any(_matches_place(rule, place) for rule in profile.excluded_places for place in lot.execution_places):
        return TenderLotMatch(lot_key=lot.lot_key, state="excluded", reason="excluded_place")
    if lot.confirmed_directions.intersection(profile.excluded_directions):
        return TenderLotMatch(lot_key=lot.lot_key, state="excluded", reason="excluded_direction")
    if lot.required_activities.intersection(profile.excluded_activities):
        return TenderLotMatch(lot_key=lot.lot_key, state="excluded", reason="excluded_activity")

    desired_directions = (set(profile.included_directions) or _HVAC_DIRECTIONS).difference(profile.excluded_directions)
    desired_activities = [set(item) for item in profile.activity_combinations]
    activity_groups = lot.activity_evidence_groups if lot.activity_evidence_groups is not None else [lot.required_activities]
    known_direction = bool(lot.confirmed_directions & desired_directions)
    known_activities = not desired_activities or any(
        required <= confirmed for required in desired_activities for confirmed in activity_groups
    )
    known_place = not profile.included_places or any(
        _matches_place(rule, place) for rule in profile.included_places for place in lot.execution_places
    )
    if not known_place and lot.places_complete:
        return TenderLotMatch(lot_key=lot.lot_key, state="excluded", reason="different_place")
    if not known_direction and lot.directions_complete:
        return TenderLotMatch(lot_key=lot.lot_key, state="excluded", reason="different_direction")
    if not known_activities and lot.activities_complete:
        return TenderLotMatch(lot_key=lot.lot_key, state="excluded", reason="different_activity")
    if not known_direction or (
        profile.excluded_directions
        and (not lot.directions_complete or lot.possible_directions.intersection(profile.excluded_directions))
    ) or (strict and not (lot.directions_complete or lot.verified_native_lot)):
        return TenderLotMatch(lot_key=lot.lot_key, state="review", reason="unconfirmed_direction")
    if not known_place or (
        (profile.excluded_places or strict and profile.included_places) and not lot.places_complete
    ):
        return TenderLotMatch(lot_key=lot.lot_key, state="review", reason="unconfirmed_place")
    if not known_activities or (
        profile.excluded_activities
        and (not lot.activities_complete or lot.possible_activities.intersection(profile.excluded_activities))
    ) or (strict and not (lot.activities_complete or lot.verified_native_lot and lot.required_activities)):
        return TenderLotMatch(lot_key=lot.lot_key, state="review", reason="unconfirmed_activity")
    return TenderLotMatch(lot_key=lot.lot_key, state="match", reason="eligible")
