"""Company tender search criteria and classified execution facts."""

import re
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TenderDirection = Literal["air_conditioning", "ventilation", "refrigeration"]
TenderActivity = Literal["maintenance", "diagnostics", "repair", "supply", "installation"]
# Canonical Belarus region codes shared with the collector. The capital and
# its surrounding oblast are distinct.
TenderRegion = Literal["1", "2", "3", "4", "5", "6", "7"]
TenderSearchMode = Literal["broad", "strict"]
TenderMatchState = Literal["match", "review", "excluded"]
TenderMatchReason = Literal[
    "eligible", "excluded_place", "excluded_direction", "excluded_activity",
    "different_place", "different_direction", "different_activity",
    "unconfirmed_place", "unconfirmed_direction", "unconfirmed_activity",
]


def normalized_place(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold().replace("ё", "е")))


class TenderPlace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: TenderRegion
    locality: str | None = Field(default=None, max_length=150)

    @field_validator("locality")
    @classmethod
    def normalize_locality(cls, value: str | None) -> str | None:
        if value is None:
            return None
        result = normalized_place(value)
        if len(result) < 2:
            raise ValueError("Укажите город или район")
        return result

    def identity(self) -> tuple[str, str | None]:
        return self.region, self.locality


_ActivityCombination = Annotated[list[TenderActivity], Field(min_length=1, max_length=5)]


class TenderSearchProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=96)
    mode: TenderSearchMode = "broad"
    included_places: list[TenderPlace] = Field(default_factory=list, max_length=30)
    excluded_places: list[TenderPlace] = Field(default_factory=list, max_length=30)
    included_directions: list[TenderDirection] = Field(default_factory=list, max_length=3)
    excluded_directions: list[TenderDirection] = Field(default_factory=list, max_length=3)
    activity_combinations: list[_ActivityCombination] = Field(default_factory=list, max_length=12)
    excluded_activities: list[TenderActivity] = Field(default_factory=list, max_length=5)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        result = " ".join(value.split())
        if not result:
            raise ValueError("Укажите название профиля")
        return result

    @model_validator(mode="after")
    def validate_rules(self):
        included = {place.identity() for place in self.included_places}
        excluded = {place.identity() for place in self.excluded_places}
        if len(included) != len(self.included_places) or len(excluded) != len(self.excluded_places):
            raise ValueError("Уберите повторяющиеся места")
        if included & excluded:
            raise ValueError("Одно место добавлено в поиск и исключения")
        if set(self.included_directions) & set(self.excluded_directions):
            raise ValueError("Одно направление добавлено в поиск и исключения")
        if any(set(combination) & set(self.excluded_activities) for combination in self.activity_combinations):
            raise ValueError("Сочетание работ содержит исключённый вид работы")
        if set(self.excluded_directions) == set(get_args(TenderDirection)):
            raise ValueError("Оставьте хотя бы одно направление")
        if set(self.excluded_activities) == set(get_args(TenderActivity)):
            raise ValueError("Оставьте хотя бы один вид работы")
        return self


class TenderLotSignals(BaseModel):
    """Facts about one lot. Possible directions or activities may come from a listing."""

    lot_key: str = Field(min_length=1, max_length=120)
    execution_places: list[TenderPlace] = Field(default_factory=list, max_length=30)
    confirmed_directions: set[TenderDirection] = Field(default_factory=set)
    possible_directions: set[TenderDirection] = Field(default_factory=set)
    required_activities: set[TenderActivity] = Field(default_factory=set)
    activity_evidence_groups: list[set[TenderActivity]] | None = None
    possible_activities: set[TenderActivity] = Field(default_factory=set)
    places_complete: bool = False
    directions_complete: bool = False
    activities_complete: bool = False
    verified_native_lot: bool = False


class TenderLotMatch(BaseModel):
    lot_key: str
    state: TenderMatchState
    reason: TenderMatchReason


class TenderModuleAccess(BaseModel):
    entitled: bool
    enabled: bool
    version: int


class TenderModuleSettings(TenderModuleAccess):
    profiles: list[TenderSearchProfile] = Field(default_factory=list)


class TenderModuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    version: int = Field(ge=0)
    profiles: list[TenderSearchProfile] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_profiles(self):
        if self.enabled and not self.profiles:
            raise ValueError("Добавьте профиль для поиска тендеров")
        if len({profile.name.casefold() for profile in self.profiles}) != len(self.profiles):
            raise ValueError("Дайте профилям разные названия")
        return self


class TenderModuleEntitlementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entitled: bool
    version: int = Field(ge=0)


class TenderProfilePreviewItem(BaseModel):
    order_id: int
    title: str
    result: TenderLotMatch
    lots: list[TenderLotMatch] = Field(default_factory=list)


class TenderProfilePreview(BaseModel):
    items: list[TenderProfilePreviewItem]
