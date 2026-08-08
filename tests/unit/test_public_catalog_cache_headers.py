import pytest
from starlette.responses import Response

from core.storefront_request_envelope import force_private_storefront_response_headers
from models.tenancy import TenantScope
from routers.api_catalog_revision import get_catalog_revision
from services.catalog_revision_service import CatalogRevisionService


@pytest.mark.asyncio
async def test_revision_etag_is_storefront_specific_and_varies_by_verified_host(
    monkeypatch,
):
    async def fake_contextual(_session, *, tenant_scope):
        storefront_revision = 3 if tenant_scope.storefront_id == 20 else 8
        return {
            "revision": 11,
            "storefront_revision": storefront_revision,
            "cache_key": f"g11-s{storefront_revision}",
            "updated_at": "2026-08-01T00:00:00+00:00",
        }

    monkeypatch.setattr(CatalogRevisionService, "get_contextual", fake_contextual)
    scope_a = TenantScope(2, 20, is_canonical_storefront=False)
    scope_b = TenantScope(2, 21, is_canonical_storefront=False)
    response_a = Response()
    response_b = Response()

    payload_a = await get_catalog_revision(
        response_a,
        session=object(),
        tenant_scope=scope_a,
    )
    payload_b = await get_catalog_revision(
        response_b,
        session=object(),
        tenant_scope=scope_b,
    )

    assert payload_a["cache_key"] == "g11-s3"
    assert payload_b["cache_key"] == "g11-s8"
    assert response_a.headers["ETag"] == 'W/"catalog-g11-s3"'
    assert response_b.headers["ETag"] == 'W/"catalog-g11-s8"'
    assert response_a.headers["Vary"] == "X-MVN-Storefront-Host"
    assert response_b.headers["Vary"] == "X-MVN-Storefront-Host"
    assert response_a.headers["Cache-Control"] == "private, no-cache, max-age=0"


def test_signed_storefront_cache_policy_preserves_etag_and_merges_vary():
    headers = force_private_storefront_response_headers(
        [
            (b"etag", b'W/"catalog-g11-s3"'),
            (b"cache-control", b"public, max-age=3600"),
            (b"cdn-cache-control", b"public, max-age=3600"),
            (b"vary", b"Accept-Encoding, accept-encoding"),
        ]
    )
    by_name = {name.lower(): value.decode("latin-1") for name, value in headers}

    assert by_name[b"etag"] == 'W/"catalog-g11-s3"'
    assert by_name[b"cache-control"] == "private, no-store"
    assert by_name[b"cdn-cache-control"] == "no-store"
    assert by_name[b"vary"] == "Accept-Encoding, X-MVN-Storefront-Host"
