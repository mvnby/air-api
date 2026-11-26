import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from api_contracts.order_travel_route import ManagerOrderTravelRouteRequest
from models.tenancy import TenantScope
from routers import manager_order_travel_route as endpoint
from services.order_travel_route_service import OrderTravelRouteError, OrderTravelRouteService


def geocoder_response(*, country="BY", kind="house", precision="exact"):
    return {
        "response": {
            "GeoObjectCollection": {
                "featureMember": [
                    {"GeoObject": {
                        "Point": {"pos": "28.6902 54.8823"},
                        "metaDataProperty": {"GeocoderMetaData": {
                            "kind": kind,
                            "precision": precision,
                            "Address": {
                                "country_code": country,
                                "formatted": "Беларусь, Лепель, площадь Свободы, 1",
                            },
                        }},
                    }},
                ],
            },
        },
    }


def install_transport(monkeypatch, handler):
    create_client = httpx.AsyncClient
    monkeypatch.delenv("ORDER_ROUTE_ORS_API_KEY", raising=False)
    monkeypatch.setenv("ORDER_ROUTE_YANDEX_GEOCODER_KEY", "test-geocoder")
    monkeypatch.setenv("ORDER_ROUTE_YANDEX_ROUTER_KEY", "test-router")
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: create_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
async def test_calculates_both_directions_using_documented_yandex_units(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        params = request.url.params
        if len(calls) == 1:
            assert params["geocode"] == "Беларусь, Лепель, площадь Свободы, 1"
            assert params["apikey"] == "test-geocoder"
            return httpx.Response(200, json=geocoder_response())
        assert params["mode"] == "driving"
        assert params["apikey"] == "test-router"
        assert params["waypoints"] == "55.1904,30.2049|54.8823,28.6902|55.1904,30.2049"
        return httpx.Response(200, json={"route": {"legs": [
            {"status": "OK", "steps": [
                {"length": 110023.4, "duration": 6412.4},
                {"length": 2501.4, "duration": 301.0},
            ]},
            {"status": "OK", "steps": [{"length": 113201.0, "duration": 6729.0}]},
        ]}})

    install_transport(monkeypatch, handler)
    route = await OrderTravelRouteService.calculate("Лепель,  площадь Свободы, 1")
    assert calls == ["geocode-maps.yandex.ru", "api.routing.yandex.net"]
    assert route.outbound.model_dump() == {"distance_m": 112525, "duration_s": 6713}
    assert route.inbound.model_dump() == {"distance_m": 113201, "duration_s": 6729}
    assert route.total.model_dump() == {"distance_m": 225726, "duration_s": 13442}
    assert route.approximate_destination is False


@pytest.mark.asyncio
async def test_ors_prioritizes_heigit_and_requests_two_driving_legs_without_geometry(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "api.heigit.org"
        assert request.headers["authorization"] == "test-heigit"
        assert "api_key" not in request.url.params
        if request.method == "GET":
            assert request.url.path == "/pelias/v1/search"
            assert request.url.params["text"] == "Ушачи, Советская улица, 1"
            assert request.url.params["boundary.country"] == "BLR"
            return httpx.Response(200, json={"features": [{
                "geometry": {"coordinates": [28.6128, 55.1813]},
                "properties": {
                    "country_a": "BLR", "layer": "address", "match_type": "exact",
                    "label": "Ушачи, Советская улица, 1",
                },
            }]})
        assert request.url.path == "/openrouteservice/v2/matrix/driving-car"
        assert json.loads(request.content) == {
            "locations": [[30.2049, 55.1904], [28.6128, 55.1813]],
            "metrics": ["distance", "duration"],
            "units": "m",
        }
        return httpx.Response(200, json={
            "distances": [[0, 114900.1], [116100.0, 0]],
            "durations": [[0, 6000.0], [6100.0, 0]],
        })

    install_transport(monkeypatch, handler)
    monkeypatch.setenv("ORDER_ROUTE_ORS_API_KEY", "test-heigit")
    result = await OrderTravelRouteService.calculate("Ушачи, Советская улица, 1")
    assert len(requests) == 2
    assert result.provider == "openrouteservice"
    assert result.destination == "Ушачи, Советская улица, 1"
    assert result.total.model_dump() == {"distance_m": 231000, "duration_s": 12100}
    assert result.approximate_destination is False


@pytest.mark.asyncio
async def test_ors_address_missing_does_not_use_yandex_or_call_matrix(monkeypatch):
    def handler(request):
        assert request.url.path == "/pelias/v1/search"
        return httpx.Response(200, json={"features": []})

    install_transport(monkeypatch, handler)
    monkeypatch.setenv("ORDER_ROUTE_ORS_API_KEY", "test-heigit")
    with pytest.raises(OrderTravelRouteError, match="order_route_address_not_found"):
        await OrderTravelRouteService.calculate("Ушачи")


def test_missing_matrix_leg_is_not_reported_as_zero_distance():
    with pytest.raises(OrderTravelRouteError, match="order_route_not_found"):
        OrderTravelRouteService._leg(None, None)


@pytest.mark.asyncio
async def test_suggest_key_does_not_enable_paid_routing(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "suggest-only")
    monkeypatch.delenv("ORDER_ROUTE_ORS_API_KEY", raising=False)
    monkeypatch.delenv("ORDER_ROUTE_YANDEX_GEOCODER_KEY", raising=False)
    monkeypatch.delenv("ORDER_ROUTE_YANDEX_ROUTER_KEY", raising=False)
    with pytest.raises(OrderTravelRouteError) as error:
        await OrderTravelRouteService.calculate("Лепель")
    assert (error.value.code, error.value.status_code) == ("order_route_not_configured", 503)


def test_city_result_is_approximate_and_foreign_candidate_is_rejected():
    assert OrderTravelRouteService._yandex_destination(geocoder_response(kind="locality"))[2]
    with pytest.raises(OrderTravelRouteError, match="order_route_address_not_found"):
        OrderTravelRouteService._yandex_destination(geocoder_response(country="RU"))


@pytest.mark.parametrize("non_address", ["+375 29 121-21-21", "contact@example.test"])
def test_legacy_contact_info_is_not_a_geocoding_address(non_address):
    with pytest.raises(ValidationError, match="an address is required"):
        ManagerOrderTravelRouteRequest(address=non_address)


@pytest.mark.parametrize(
    ("provider_status", "expected_code", "expected_status"),
    [(403, "order_route_not_configured", 503), (429, "order_route_provider_limit", 503),
     (502, "order_route_unavailable", 502)],
)
@pytest.mark.asyncio
async def test_upstream_errors_expose_only_stable_codes(monkeypatch, provider_status, expected_code, expected_status):
    install_transport(monkeypatch, lambda req: httpx.Response(provider_status, text=str(req.url)))
    with pytest.raises(OrderTravelRouteError) as error:
        await OrderTravelRouteService.calculate("Лепель")
    assert str(error.value) == expected_code
    assert error.value.status_code == expected_status


@pytest.mark.asyncio
async def test_order_scope_is_checked_before_provider_call(monkeypatch):
    scope = TenantScope(tenant_id=17, storefront_id=19, is_system=True)
    auth = SimpleNamespace(tenant_scope=lambda: scope, staff_user_id=2, username="test")
    access = AsyncMock(return_value=None)
    calculate = AsyncMock()
    session = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(endpoint.TenantEntityAccessService, "get_order", access)
    monkeypatch.setattr(endpoint.OrderTravelRouteService, "calculate", calculate)

    with pytest.raises(HTTPException) as error:
        await endpoint.calculate_manager_order_travel_route(
            699, ManagerOrderTravelRouteRequest(address="Лепель"), Response(), auth, session,
        )
    assert error.value.status_code == 404
    access.assert_awaited_once_with(session, 699, tenant_scope=scope)
    calculate.assert_not_awaited()


@pytest.mark.asyncio
async def test_partner_orders_do_not_use_mvn_routing_quota(monkeypatch):
    scope = TenantScope(tenant_id=17, storefront_id=19)
    auth = SimpleNamespace(tenant_scope=lambda: scope, staff_user_id=2, username="test")
    calculate = AsyncMock()
    monkeypatch.setattr(endpoint.OrderTravelRouteService, "calculate", calculate)

    with pytest.raises(HTTPException) as error:
        await endpoint.calculate_manager_order_travel_route(
            699, ManagerOrderTravelRouteRequest(address="Лепель"), Response(), auth, None,
        )
    assert error.value.status_code == 403
    calculate.assert_not_awaited()
