from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from core.demo_access import enforce_demo_read_only


def _request(method, operation_id="new_manager_operation"):
    return Request({
        "type": "http", "method": method, "path": "/api/manager/example",
        "headers": [], "route": SimpleNamespace(operation_id=operation_id),
    })


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_demo_rejects_unlisted_writes_including_future_operations(method):
    with pytest.raises(HTTPException) as error:
        enforce_demo_read_only(_request(method), demo_read_only=True)
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "demo_read_only"


@pytest.mark.parametrize("operation_id", [
    "calculate_manager_install_estimate", "calculate_public_service_tariff",
])
def test_demo_permits_pure_calculators_only_as_post(operation_id):
    enforce_demo_read_only(_request("POST", operation_id), demo_read_only=True)
    with pytest.raises(HTTPException):
        enforce_demo_read_only(_request("PUT", operation_id), demo_read_only=True)


def test_demo_rejects_installation_preview_because_it_stores_a_receipt():
    with pytest.raises(HTTPException) as error:
        enforce_demo_read_only(_request("POST", "preview_public_installation_estimate"), demo_read_only=True)
    assert error.value.status_code == 403


@pytest.mark.parametrize("operation_id", [
    "get_manager_document_drive_authorization_url", "get_manager_google_auth_url",
    "get_manager_managed_document_google_edit_session",
    "get_manager_native_template_google_edit_session",
])
def test_demo_cannot_start_external_connection_even_over_get(operation_id):
    with pytest.raises(HTTPException):
        enforce_demo_read_only(_request("GET", operation_id), demo_read_only=True)


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_demo_allows_reads(method):
    enforce_demo_read_only(_request(method), demo_read_only=True)


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_normal_tenant_retains_existing_access_policy(method):
    enforce_demo_read_only(_request(method), demo_read_only=False)


@pytest.mark.asyncio
async def test_public_demo_scope_keeps_calculator_but_prevents_form_submissions():
    from core.tenant_scope import VerifiedPublicStorefrontRequest, get_public_tenant_scope
    from services.storefront_context_service import StorefrontContext

    verified = VerifiedPublicStorefrontRequest(signed=True, context=StorefrontContext(
        tenant_id=35, tenant_slug="test1", tenant_kind="independent_seller",
        storefront_id=36, storefront_slug="main", storefront_name="Test 1",
        hostname="test1.mvn.by", city=None, default_locale="ru-BY", currency="BYN",
        demo_read_only=True,
    ))
    scope = await get_public_tenant_scope(
        _request("POST", "calculate_public_service_tariff"), verified=verified,
        session=None,
    )
    assert scope.tenant_id == 35
    assert scope.storefront_id == 36
    assert scope.demo_read_only is True
    with pytest.raises(HTTPException) as error:
        await get_public_tenant_scope(
            _request("POST", "create_order"), verified=verified, session=None,
        )
    assert error.value.detail["code"] == "demo_read_only"
