import pytest

from services.catalog_media_policy import CatalogMediaKind, CatalogMediaPolicy


CONTENT_HASH = "a" * 64


@pytest.mark.parametrize(
    ("kind", "url"),
    [
        (CatalogMediaKind.PRODUCT, "https://cdn.mvn.by/products/shared/model.webp"),
        (
            CatalogMediaKind.PRODUCT,
            "https://cdn.mvn.by/products/variants/original/MODEL.JPEG",
        ),
        (
            CatalogMediaKind.CONTENT,
            f"https://cdn.mvn.by/library/original/{CONTENT_HASH}.svg",
        ),
        (
            CatalogMediaKind.SERIES,
            f"https://cdn.mvn.by/library/original/{CONTENT_HASH}.webp",
        ),
        (CatalogMediaKind.SERIES, "https://cdn.mvn.by/products/shared/model.webp"),
    ],
)
def test_catalog_media_policy_accepts_partner_renderable_urls(kind, url):
    assert CatalogMediaPolicy.is_allowed(url, kind=kind)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/logo.svg",
        f"https://cdn.mvn.by/media/library/original/{CONTENT_HASH}.svg",
        f"https://cdn.mvn.by/library/original/{CONTENT_HASH}.svg?download=1",
        f"https://cdn.mvn.by:bad/library/original/{CONTENT_HASH}.svg",
        f"https://CDN.mvn.by/library/original/{CONTENT_HASH}.svg",
        f"https://cdn.mvn.by/library/original/{CONTENT_HASH[:-1]}.svg",
        f"https://cdn.mvn.by/library/processed/{CONTENT_HASH}.svg",
    ],
)
def test_catalog_media_policy_rejects_urls_hidden_by_partner_storefront(url):
    assert not CatalogMediaPolicy.is_allowed(url, kind=CatalogMediaKind.CONTENT)


def test_catalog_media_policy_keeps_svg_out_of_product_media():
    assert not CatalogMediaPolicy.is_allowed(
        f"https://cdn.mvn.by/products/shared/{CONTENT_HASH}.svg",
        kind=CatalogMediaKind.PRODUCT,
    )


def test_catalog_media_policy_accepts_local_managed_urls_only_for_local_provider(monkeypatch):
    content_url = f"/media/library/original/{CONTENT_HASH}.svg"
    product_url = "/media/products/shared/model.webp"
    monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER", "local")
    assert CatalogMediaPolicy.is_allowed(content_url, kind=CatalogMediaKind.CONTENT)
    assert CatalogMediaPolicy.is_allowed(product_url, kind=CatalogMediaKind.PRODUCT)

    monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
    monkeypatch.setenv("PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER", "r2")
    assert not CatalogMediaPolicy.is_allowed(content_url, kind=CatalogMediaKind.CONTENT)
    assert not CatalogMediaPolicy.is_allowed(product_url, kind=CatalogMediaKind.PRODUCT)


def test_catalog_media_policy_preserves_semantic_feature_icons():
    assert (
        CatalogMediaPolicy.require_optional_content_reference("wifi", field="feature.icon")
        == "wifi"
    )
