from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator


class ManagerOrderTravelRouteRequest(BaseModel):
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=240)]

    @field_validator("address")
    @classmethod
    def require_address_text(cls, value: str) -> str:
        # Legacy orders can carry a phone number in the delivery address field.
        if not any(char.isalpha() for char in value) or "@" in value:
            raise ValueError("an address is required")
        return value


class OrderTravelLeg(BaseModel):
    distance_m: int = Field(ge=0)
    duration_s: int = Field(ge=0)


class ManagerOrderTravelRouteResponse(BaseModel):
    provider: Literal["openrouteservice", "yandex"]
    origin: str
    destination: str
    approximate_destination: bool
    outbound: OrderTravelLeg
    inbound: OrderTravelLeg
    total: OrderTravelLeg
