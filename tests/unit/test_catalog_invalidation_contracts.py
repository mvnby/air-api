import pytest
from pydantic import ValidationError

from services.catalog_invalidation_contracts import (
    CatalogCacheInvalidationRequestedV1,
)


def _payload(**overrides):
    payload = {
        "schema_version": 1,
        "scope": "storefront",
        "tenant_id": 2,
        "storefront_id": 3,
        "origins": ["HTTPS://Shop.MVN.BY:443/", "https://mvn.by"],
        "paths": ["/product/z/", "/catalog/", "/product/a/"],
        "global_revision": 4,
        "storefront_revision": 5,
        "cache_key": "g4-s5",
        "reason": "tenant_offer_updated",
    }
    payload.update(overrides)
    return payload


def test_catalog_invalidation_payload_is_canonical_and_exact():
    event = CatalogCacheInvalidationRequestedV1.model_validate(_payload())

    assert event.origins == ["https://mvn.by", "https://shop.mvn.by"]
    assert event.paths == ["/catalog/", "/product/a/", "/product/z/"]
    assert set(event.model_dump()) == {
        "schema_version",
        "scope",
        "tenant_id",
        "storefront_id",
        "origins",
        "paths",
        "global_revision",
        "storefront_revision",
        "cache_key",
        "reason",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"cache_key": "g4-s6"},
        {"origins": ["https://user:password@mvn.by"]},
        {"paths": ["https://mvn.by/catalog/"]},
        {"paths": ["/catalog/\\poison"]},
        {"paths": ["/catalog/\npoison"]},
        {"paths": ["/" + ("a" * 2048)]},
        {"reason": "Tenant Offer Updated"},
        {"unexpected": "field"},
    ],
)
def test_catalog_invalidation_payload_rejects_inconsistent_or_untrusted_data(
    overrides,
):
    with pytest.raises(ValidationError):
        CatalogCacheInvalidationRequestedV1.model_validate(
            _payload(**overrides)
        )


def test_empty_origins_are_the_explicit_non_routable_storefront_contract():
    event = CatalogCacheInvalidationRequestedV1.model_validate(
        _payload(origins=[])
    )

    assert event.origins == []
