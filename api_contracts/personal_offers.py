"""Manager draft inputs and the explicitly public offer projection."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator


InstallationMode = Literal["none", "unknown", "fixed"]
OfferWifi = Literal["builtin", "ready", "none"]
Price = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]
InstallationPrice = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
OfferTitle = Annotated[str, Field(max_length=100)]
OfferNote = Annotated[str, Field(max_length=500)]


class PersonalOfferInstallationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: InstallationMode
    price_byn: InstallationPrice | None = None
    description: OfferNote | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> PersonalOfferInstallationInput:
        if (self.mode == "fixed") != (self.price_byn is not None):
            raise ValueError("Укажите цену только для монтажа с фиксированной стоимостью.")
        return self


class PersonalOfferOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_id: int = Field(gt=0)
    price_byn: Price
    note: OfferNote | None = None


class PersonalOfferRoomInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: OfferTitle | None = None
    installation: PersonalOfferInstallationInput
    options: list[PersonalOfferOptionInput] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def distinct_options(self) -> PersonalOfferRoomInput:
        if len({option.product_id for option in self.options}) != len(self.options):
            raise ValueError("В одном помещении каждая модель может быть указана только один раз.")
        return self


class PersonalOfferDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: int | None = Field(default=None, gt=0)
    expires_at: AwareDatetime
    rooms: list[PersonalOfferRoomInput] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def limit_total_options(self) -> PersonalOfferDraftInput:
        if sum(len(room.options) for room in self.rooms) > 48:
            raise ValueError("В одном предложении можно указать до 48 вариантов.")
        return self


class PersonalOfferUpdateInput(PersonalOfferDraftInput):
    expected_version: int = Field(gt=0)


class PersonalOfferVersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)


class PersonalOfferPublishInput(PersonalOfferVersionInput):
    request_id: UUID


class ManagerPersonalOfferPublished(BaseModel):
    url: str
    expires_at: AwareDatetime


class ManagerPersonalOfferResponse(PersonalOfferDraftInput):
    id: int
    version: int
    published: ManagerPersonalOfferPublished | None


class ManagerPersonalOfferListResponse(BaseModel):
    items: list[ManagerPersonalOfferResponse]
    has_more: bool


class PublicPersonalOfferInstallation(BaseModel):
    mode: InstallationMode
    price_byn: Decimal | None
    description: str | None


class PublicPersonalOfferOption(BaseModel):
    title: str
    slug: str | None
    main_image: str | None
    price_byn: Decimal
    original_price_byn: Decimal | None
    total_price_byn: Decimal | None
    note: str | None
    cooling_power_kw: FiniteFloat | None
    noise_indoor_min_db: FiniteFloat | None
    is_inverter: bool | None
    wifi: OfferWifi | None


class PublicPersonalOfferRoom(BaseModel):
    title: str
    installation: PublicPersonalOfferInstallation
    options: list[PublicPersonalOfferOption]


class PublicPersonalOfferResponse(BaseModel):
    expires_at: AwareDatetime
    rooms: list[PublicPersonalOfferRoom]
