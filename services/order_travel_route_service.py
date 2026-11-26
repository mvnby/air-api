"""Driving distance and time from Vitebsk for an order address."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import httpx

from api_contracts.order_travel_route import ManagerOrderTravelRouteResponse, OrderTravelLeg
from services.address_suggest_service import AddressSuggestService
from services.postal_address_service import normalize_postal_address


_SETTLEMENT_PREFIX = re.compile(
    r"^(?:г\.?\s*п\.|р\.?\s*п\.|город\s+|горад\s+|г\.|деревня\s+|в[её]ска\s+|д\.|в\.|"
    r"агрогородок\s+|аграгарадок\s+|а/г\.?|аг\.|пос[её]лок\s+|п\.|м\.)\s*",
    re.IGNORECASE,
)
_PLACE_NAME = re.compile(r"[А-ЯЁІЎа-яёіў]+(?:[ \-’'][А-ЯЁІЎа-яёіў]+){0,4}")


class OrderTravelRouteError(RuntimeError):
    def __init__(self, code: str, status_code: int):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class OrderTravelRouteService:
    PELIAS_URL = "https://api.heigit.org/pelias/v1/search"
    ORS_MATRIX_URL = "https://api.heigit.org/openrouteservice/v2/matrix/driving-car"
    ORIGIN_LABEL = "Витебск, центр города"

    @classmethod
    async def calculate(cls, address: str) -> ManagerOrderTravelRouteResponse:
        key = os.getenv("ORDER_ROUTE_ORS_API_KEY", "").strip()
        if not key:
            raise OrderTravelRouteError("order_route_not_configured", 503)

        settlement, query = cls._settlement_query(address)
        longitude, latitude = map(float, AddressSuggestService.VITEBSK_CENTER.split(","))
        headers = {"Authorization": key}
        try:
            async with asyncio.timeout(9):
                async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                    point = await cls._find_settlement(client, query, headers)
                    matrix = await cls._request(client, "POST", cls.ORS_MATRIX_URL, headers=headers, json={
                        "locations": [(longitude, latitude), point],
                        "metrics": ["distance", "duration"],
                        "units": "m",
                    })
            distances, durations = matrix["distances"], matrix["durations"]
            outbound = cls._leg(distances[0][1], durations[0][1])
            inbound = cls._leg(distances[1][0], durations[1][0])
        except OrderTravelRouteError:
            raise
        except (TimeoutError, httpx.HTTPError, AttributeError, IndexError, KeyError, TypeError, ValueError):
            raise OrderTravelRouteError("order_route_unavailable", 502) from None

        return ManagerOrderTravelRouteResponse(
            provider="openrouteservice",
            origin=cls.ORIGIN_LABEL,
            destination=settlement,
            approximate_destination=True,
            outbound=outbound,
            inbound=inbound,
            total=OrderTravelLeg(
                distance_m=outbound.distance_m + inbound.distance_m,
                duration_s=outbound.duration_s + inbound.duration_s,
            ),
        )

    @staticmethod
    def _settlement_query(address: str) -> tuple[str, str]:
        # The hosted HeiGIT terms exclude transmitting personal data.
        # Resolve the locality separately so street, house and contact details stay in Manager.
        normalized = normalize_postal_address(address, "")
        locality = normalized.postal_line
        if not locality and not normalized.area_lines and not re.search(r"[,;\r\n]", address):
            locality = " ".join(address.split())
        settlement = _SETTLEMENT_PREFIX.sub("", locality)
        if not _PLACE_NAME.fullmatch(settlement) or len(settlement) > 80:
            raise OrderTravelRouteError("order_route_settlement_required", 422)
        areas = [area for area in normalized.area_lines if len(area) <= 80 and _PLACE_NAME.fullmatch(area)]
        return settlement, ", ".join([settlement, *areas])

    @classmethod
    async def _find_settlement(
        cls, client: httpx.AsyncClient, query: str, headers: dict[str, str],
    ) -> tuple[float, float]:
        geocode = await cls._request(client, "GET", cls.PELIAS_URL, headers=headers, params={
            "text": query,
            "boundary.country": "BLR",
            "layers": "locality,localadmin",
            "size": 1,
        })
        features = geocode["features"]
        if not features:
            raise OrderTravelRouteError("order_route_address_not_found", 422)

        found = features[0]
        properties = found["properties"]
        lon, lat = found["geometry"]["coordinates"]
        if (
            properties.get("layer") not in {"locality", "localadmin"}
            or properties.get("match_type") != "exact"
            or properties.get("country_a") != "BLR"
            or not (51.2 <= lat <= 56.4 and 23.1 <= lon <= 32.8)
        ):
            raise OrderTravelRouteError("order_route_address_not_found", 422)
        return lon, lat

    @staticmethod
    async def _request(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> dict:
        response = await client.request(method, url, **kwargs)
        if response.status_code in (401, 403):
            raise OrderTravelRouteError("order_route_not_configured", 503)
        if response.status_code == 429:
            raise OrderTravelRouteError("order_route_provider_limit", 503)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _leg(distance: float | None, duration: float | None) -> OrderTravelLeg:
        if distance is None or duration is None:
            raise OrderTravelRouteError("order_route_not_found", 422)
        if not (0 <= distance < 10_000_000 and 0 <= duration < 1_000_000):
            raise ValueError("invalid driving totals")
        return OrderTravelLeg(distance_m=round(distance), duration_s=round(duration))
