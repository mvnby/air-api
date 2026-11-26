from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class ManagerOrderTravelRouteRequest(BaseModel):
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=240)]


class OrderTravelLeg(BaseModel):
    distance_m: int = Field(ge=0)
    duration_s: int = Field(ge=0)


class ManagerOrderTravelRouteResponse(BaseModel):
    provider: Literal["yandex"]
    origin: str
    destination: str
    approximate_destination: bool
    outbound: OrderTravelLeg
    inbound: OrderTravelLeg
    total: OrderTravelLeg
