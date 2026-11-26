from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException, Response

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
async def test_suggest_key_does_not_enable_paid_routing(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "suggest-only")
    monkeypatch.delenv("ORDER_ROUTE_YANDEX_GEOCODER_KEY", raising=False)
    monkeypatch.delenv("ORDER_ROUTE_YANDEX_ROUTER_KEY", raising=False)
    with pytest.raises(OrderTravelRouteError) as error:
        await OrderTravelRouteService.calculate("Лепель")
    assert (error.value.code, error.value.status_code) == ("order_route_not_configured", 503)


def test_city_result_is_approximate_and_foreign_candidate_is_rejected():
    assert OrderTravelRouteService._destination(geocoder_response(kind="locality"))[2]
    with pytest.raises(OrderTravelRouteError, match="order_route_address_not_found"):
        OrderTravelRouteService._destination(geocoder_response(country="RU"))


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
