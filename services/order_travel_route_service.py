"""Driving distance and time from Vitebsk for an order address."""

from __future__ import annotations

import asyncio
import os

import httpx

from api_contracts.order_travel_route import ManagerOrderTravelRouteResponse, OrderTravelLeg
from services.address_suggest_service import AddressSuggestService


class OrderTravelRouteError(RuntimeError):
    def __init__(self, code: str, status_code: int):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class OrderTravelRouteService:
    GEOCODER_URL = "https://geocode-maps.yandex.ru/v1/"
    ROUTER_URL = "https://api.routing.yandex.net/v2/route"
    ORIGIN_LABEL = "Витебск, центр города"

    @classmethod
    async def calculate(cls, address: str) -> ManagerOrderTravelRouteResponse:
        geocoder_key = os.getenv("ORDER_ROUTE_YANDEX_GEOCODER_KEY", "").strip()
        router_key = os.getenv("ORDER_ROUTE_YANDEX_ROUTER_KEY", "").strip()
        if not geocoder_key or not router_key:
            raise OrderTravelRouteError("order_route_not_configured", 503)

        origin_lon, origin_lat = AddressSuggestService.VITEBSK_CENTER.split(",")
        origin = f"{origin_lat},{origin_lon}"
        try:
            async with asyncio.timeout(9):
                async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                    geocode = await cls._get(client, cls.GEOCODER_URL, {
                        "apikey": geocoder_key,
                        "geocode": f"Беларусь, {' '.join(address.split())}",
                        "lang": "ru_BY",
                        "format": "json",
                        "results": 1,
                        "bbox": AddressSuggestService.BELARUS_BBOX,
                        "rspn": 1,
                    })
                    destination, point, approximate = cls._destination(geocode)
                    route = await cls._get(client, cls.ROUTER_URL, {
                        "apikey": router_key,
                        "mode": "driving",
                        "waypoints": f"{origin}|{point}|{origin}",
                    })
            outbound, inbound = cls._road_legs(route)
        except OrderTravelRouteError:
            raise
        except (TimeoutError, httpx.HTTPError, AttributeError, IndexError, KeyError, TypeError, ValueError):
            raise OrderTravelRouteError("order_route_unavailable", 502) from None

        return ManagerOrderTravelRouteResponse(
            provider="yandex",
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

    @staticmethod
    async def _get(client: httpx.AsyncClient, url: str, params: dict) -> dict:
        response = await client.get(url, params=params)
        if response.status_code in (401, 403):
            raise OrderTravelRouteError("order_route_not_configured", 503)
        if response.status_code == 429:
            raise OrderTravelRouteError("order_route_provider_limit", 503)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _destination(payload: dict) -> tuple[str, str, bool]:
        matches = payload["response"]["GeoObjectCollection"]["featureMember"]
        if not matches:
            raise OrderTravelRouteError("order_route_address_not_found", 422)
        item = matches[0]["GeoObject"]
        meta = item["metaDataProperty"]["GeocoderMetaData"]
        kind = meta.get("kind")
        address = meta["Address"]
        if address.get("country_code", "").upper() != "BY" or kind not in {
            "house", "street", "locality", "district",
        }:
            raise OrderTravelRouteError("order_route_address_not_found", 422)
        lon, lat = map(float, item["Point"]["pos"].split())
        if not (51.2 <= lat <= 56.4 and 23.1 <= lon <= 32.8):
            raise OrderTravelRouteError("order_route_address_not_found", 422)
        label = address.get("formatted") or meta["text"]
        return label, f"{lat},{lon}", kind != "house" or meta.get("precision") != "exact"

    @classmethod
    def _road_legs(cls, payload: dict) -> tuple[OrderTravelLeg, OrderTravelLeg]:
        legs = payload["route"]["legs"]
        if len(legs) != 2:
            raise ValueError("expected two driving legs")
        return cls._road_leg(legs[0]), cls._road_leg(legs[1])

    @staticmethod
    def _road_leg(leg: dict) -> OrderTravelLeg:
        if leg["status"] != "OK":
            raise OrderTravelRouteError("order_route_not_found", 422)
        steps = leg["steps"]
        if not steps:
            raise ValueError("expected driving steps")
        distance = sum(step["length"] for step in steps)
        duration = sum(step["duration"] for step in steps)
        if not (0 <= distance < 10_000_000 and 0 <= duration < 1_000_000):
            raise ValueError("invalid driving totals")
        return OrderTravelLeg(distance_m=round(distance), duration_s=round(duration))
