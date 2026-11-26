"""Driving distance and time from Vitebsk for an order address."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Literal

import httpx

from api_contracts.order_travel_route import ManagerOrderTravelRouteResponse, OrderTravelLeg
from services.address_suggest_service import AddressSuggestService


class OrderTravelRouteError(RuntimeError):
    def __init__(self, code: str, status_code: int):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class OrderTravelRouteService:
    PELIAS_URL = "https://api.heigit.org/pelias/v1/search"
    ORS_MATRIX_URL = "https://api.heigit.org/openrouteservice/v2/matrix/driving-car"
    YANDEX_GEOCODER_URL = "https://geocode-maps.yandex.ru/v1/"
    YANDEX_ROUTER_URL = "https://api.routing.yandex.net/v2/route"
    ORIGIN_LABEL = "Витебск, центр города"

    @classmethod
    async def calculate(cls, address: str) -> ManagerOrderTravelRouteResponse:
        ors_key = os.getenv("ORDER_ROUTE_ORS_API_KEY", "").strip()
        geocoder_key = os.getenv("ORDER_ROUTE_YANDEX_GEOCODER_KEY", "").strip()
        router_key = os.getenv("ORDER_ROUTE_YANDEX_ROUTER_KEY", "").strip()
        if not ors_key and not (geocoder_key and router_key):
            raise OrderTravelRouteError("order_route_not_configured", 503)

        query = " ".join(address.split())
        longitude, latitude = map(float, AddressSuggestService.VITEBSK_CENTER.split(","))
        origin = longitude, latitude
        provider: Literal["openrouteservice", "yandex"] = "openrouteservice" if ors_key else "yandex"
        try:
            async with asyncio.timeout(9):
                async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                    if ors_key:
                        destination, approximate, outbound, inbound = await cls._openrouteservice(
                            client, query, origin, ors_key,
                        )
                    else:
                        destination, approximate, outbound, inbound = await cls._yandex(
                            client, query, origin, geocoder_key, router_key,
                        )
        except OrderTravelRouteError:
            raise
        except (TimeoutError, httpx.HTTPError, AttributeError, IndexError, KeyError, TypeError, ValueError):
            raise OrderTravelRouteError("order_route_unavailable", 502) from None

        return ManagerOrderTravelRouteResponse(
            provider=provider,
            origin=cls.ORIGIN_LABEL,
            destination=destination,
            approximate_destination=approximate,
            outbound=outbound,
            inbound=inbound,
            total=OrderTravelLeg(
                distance_m=outbound.distance_m + inbound.distance_m,
                duration_s=outbound.duration_s + inbound.duration_s,
            ),
        )

    @classmethod
    async def _openrouteservice(
        cls, client: httpx.AsyncClient, address: str, origin: tuple[float, float], key: str,
    ) -> tuple[str, bool, OrderTravelLeg, OrderTravelLeg]:
        headers = {"Authorization": key}
        geocode = await cls._request(client, "GET", cls.PELIAS_URL, headers=headers, params={
            "text": address,
            "boundary.country": "BLR",
            "layers": "address,street,locality,localadmin",
            "size": 1,
        })
        features = geocode["features"]
        if not features:
            raise OrderTravelRouteError("order_route_address_not_found", 422)

        found = features[0]
        properties = found["properties"]
        point = cls._belarus_point(*found["geometry"]["coordinates"], properties.get("country_a"))
        approximate = properties.get("layer") != "address" or properties.get("match_type") != "exact"
        data = await cls._request(client, "POST", cls.ORS_MATRIX_URL, headers=headers, json={
            "locations": [origin, point],
            "metrics": ["distance", "duration"],
            "units": "m",
        })
        distances, durations = data["distances"], data["durations"]
        return (
            properties["label"],
            approximate,
            cls._leg(distances[0][1], durations[0][1]),
            cls._leg(distances[1][0], durations[1][0]),
        )

    @classmethod
    async def _yandex(
        cls, client: httpx.AsyncClient, address: str, origin: tuple[float, float],
        geocoder_key: str, router_key: str,
    ) -> tuple[str, bool, OrderTravelLeg, OrderTravelLeg]:
        geocode = await cls._request(client, "GET", cls.YANDEX_GEOCODER_URL, params={
            "apikey": geocoder_key,
            "geocode": f"Беларусь, {address}",
            "lang": "ru_BY",
            "format": "json",
            "results": 1,
            "bbox": AddressSuggestService.BELARUS_BBOX,
            "rspn": 1,
        })
        destination, point, approximate = cls._yandex_destination(geocode)
        waypoints = "|".join(f"{lat},{lon}" for lon, lat in (origin, point, origin))
        route = await cls._request(client, "GET", cls.YANDEX_ROUTER_URL, params={
            "apikey": router_key,
            "mode": "driving",
            "waypoints": waypoints,
        })
        outbound, inbound = cls._yandex_legs(route)
        return destination, approximate, outbound, inbound

    @staticmethod
    async def _request(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> dict:
        response = await client.request(method, url, **kwargs)
        if response.status_code in (401, 403):
            raise OrderTravelRouteError("order_route_not_configured", 503)
        if response.status_code == 429:
            raise OrderTravelRouteError("order_route_provider_limit", 503)
        response.raise_for_status()
        return response.json()

    @classmethod
    def _yandex_destination(cls, payload: dict) -> tuple[str, tuple[float, float], bool]:
        matches = payload["response"]["GeoObjectCollection"]["featureMember"]
        if not matches:
            raise OrderTravelRouteError("order_route_address_not_found", 422)
        item = matches[0]["GeoObject"]
        meta = item["metaDataProperty"]["GeocoderMetaData"]
        kind = meta.get("kind")
        address = meta["Address"]
        if kind not in {"house", "street", "locality", "district"}:
            raise OrderTravelRouteError("order_route_address_not_found", 422)
        lon, lat = map(float, item["Point"]["pos"].split())
        point = cls._belarus_point(lon, lat, address.get("country_code"))
        label = address.get("formatted") or meta["text"]
        return label, point, kind != "house" or meta.get("precision") != "exact"

    @staticmethod
    def _belarus_point(lon: float, lat: float, country: str | None) -> tuple[float, float]:
        if (country or "").upper() not in {"BY", "BLR"} or not (51.2 <= lat <= 56.4 and 23.1 <= lon <= 32.8):
            raise OrderTravelRouteError("order_route_address_not_found", 422)
        return lon, lat

    @classmethod
    def _yandex_legs(cls, payload: dict) -> tuple[OrderTravelLeg, OrderTravelLeg]:
        legs = payload["route"]["legs"]
        if len(legs) != 2:
            raise ValueError("expected two driving legs")
        return cls._yandex_leg(legs[0]), cls._yandex_leg(legs[1])

    @classmethod
    def _yandex_leg(cls, leg: dict) -> OrderTravelLeg:
        if leg["status"] != "OK":
            raise OrderTravelRouteError("order_route_not_found", 422)
        steps = leg["steps"]
        if not steps:
            raise ValueError("expected driving steps")
        return cls._leg(sum(step["length"] for step in steps), sum(step["duration"] for step in steps))

    @staticmethod
    def _leg(distance: float | None, duration: float | None) -> OrderTravelLeg:
        if distance is None or duration is None:
            raise OrderTravelRouteError("order_route_not_found", 422)
        if not (0 <= distance < 10_000_000 and 0 <= duration < 1_000_000):
            raise ValueError("invalid driving totals")
        return OrderTravelLeg(distance_m=round(distance), duration_s=round(duration))
