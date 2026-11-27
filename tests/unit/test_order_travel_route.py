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
from services.address_suggest_service import AddressSuggestService
from services.order_travel_route_service import OrderTravelRouteError, OrderTravelRouteService


def install_transport(monkeypatch, handler):
    create_client = httpx.AsyncClient
    monkeypatch.setenv("ORDER_ROUTE_ORS_API_KEY", "test-heigit")
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: create_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
async def test_only_locality_goes_to_heigit_and_one_matrix_returns_two_legs(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "api.heigit.org"
        assert request.headers["authorization"] == "test-heigit"
        assert "api_key" not in request.url.params
        if request.method == "GET":
            assert request.url.path == "/pelias/v1/search"
            assert request.url.params["text"] == "Лепель"
            assert request.url.params["layers"] == "locality,localadmin"
            assert request.url.params["boundary.country"] == "BLR"
            return httpx.Response(200, json={"features": [{
                "geometry": {"coordinates": [28.6902, 54.8823]},
                "properties": {
                    "country_a": "BLR", "layer": "locality", "match_type": "exact",
                    "label": "Lyepyel', VI, Belarus",
                },
            }]})
        assert request.url.path == "/openrouteservice/v2/matrix/driving-car"
        assert json.loads(request.content) == {
            "locations": [[30.2049, 55.1904], [28.6902, 54.8823]],
            "metrics": ["distance", "duration"],
            "units": "m",
        }
        return httpx.Response(200, json={
            "distances": [[0, 114900.1], [116100.0, 0]],
            "durations": [[0, 6000.0], [6100.0, 0]],
        })

    install_transport(monkeypatch, handler)
    result = await OrderTravelRouteService.calculate(
        "Учреждение, Лепель, Советская улица, д. 1, кв. 3, контакт Иван",
    )
    assert len(requests) == 2
    assert result.provider == "openrouteservice"
    assert result.destination == "Лепель"
    assert result.total.model_dump() == {"distance_m": 231000, "duration_s": 12100}
    assert result.approximate_destination is True


@pytest.mark.asyncio
async def test_ors_address_missing_does_not_call_matrix(monkeypatch):
    def handler(request):
        assert request.url.path == "/pelias/v1/search"
        return httpx.Response(200, json={"features": []})

    install_transport(monkeypatch, handler)
    with pytest.raises(OrderTravelRouteError, match="order_route_address_not_found"):
        await OrderTravelRouteService.calculate("Ушачи")


def test_missing_matrix_leg_is_not_reported_as_zero_distance():
    with pytest.raises(OrderTravelRouteError, match="order_route_not_found"):
        OrderTravelRouteService._leg(None, None)


@pytest.mark.asyncio
async def test_suggest_key_does_not_enable_routing(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "suggest-only")
    monkeypatch.delenv("ORDER_ROUTE_ORS_API_KEY", raising=False)
    with pytest.raises(OrderTravelRouteError) as error:
        await OrderTravelRouteService.calculate("Лепель")
    assert (error.value.code, error.value.status_code) == ("order_route_not_configured", 503)


@pytest.mark.parametrize(("layer", "match_type", "country"), [
    ("address", "exact", "BLR"), ("locality", "fallback", "BLR"), ("locality", "exact", "RUS"),
])
@pytest.mark.asyncio
async def test_unrelated_or_nonlocal_geocoder_result_is_rejected(monkeypatch, layer, match_type, country):
    def handler(request):
        assert request.url.path == "/pelias/v1/search"
        return httpx.Response(200, json={"features": [{
            "geometry": {"coordinates": [28.6902, 54.8823]},
            "properties": {"country_a": country, "layer": layer, "match_type": match_type},
        }]})

    install_transport(monkeypatch, handler)
    with pytest.raises(OrderTravelRouteError, match="order_route_address_not_found"):
        await OrderTravelRouteService.calculate("Лепель")


@pytest.mark.parametrize(("address", "settlement", "query"), [
    ("Ушачи", "Ушачи", "Ушачи"),
    ("Ушачи, Витебская область", "Ушачи", "Ушачи, Витебская область"),
    ("г.п. Ушачи, ул. Советская, 2", "Ушачи", "Ушачи"),
    ("Лепель, площадь Свободы, 1", "Лепель", "Лепель"),
    ("Учреждение, Лепель, пл. Свободы, д. 1", "Лепель", "Лепель"),
    ("ул. Мира, 1, аг. Копти, Витебский район", "Копти", "Копти, Витебский район"),
])
def test_extract_settlement_for_routing(address, settlement, query):
    assert OrderTravelRouteService._settlement_query(address) == (settlement, query)


@pytest.mark.parametrize(("title", "subtitle", "expected"), [
    ("Банк, 6, 3-я Коллективная улица", "Витебск", ("Витебск", "Витебск")),
    (
        "Витебская улица, 14",
        "агрогородок Новка, Новкинский сельсовет, Витебский район",
        ("Новка", "Новка, Витебский район"),
    ),
    (
        "Советская улица, 1",
        "городской посёлок Ушачи, Ушачский район",
        ("Ушачи", "Ушачи, Ушачский район"),
    ),
])
def test_extract_settlement_from_the_same_address_manager_saves_from_suggestions(title, subtitle, expected):
    [suggestion] = AddressSuggestService.normalize_results({
        "results": [{"title": {"text": title}, "subtitle": {"text": subtitle}}],
    })
    assert OrderTravelRouteService._settlement_query(suggestion["value"]) == expected


@pytest.mark.asyncio
async def test_address_without_settlement_does_not_call_provider(monkeypatch):
    def handler(request):
        pytest.fail("provider call without settlement")

    install_transport(monkeypatch, handler)
    with pytest.raises(OrderTravelRouteError, match="order_route_settlement_required"):
        await OrderTravelRouteService.calculate("ул. Советская, 1, кв. 3")


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
