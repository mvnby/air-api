from __future__ import annotations

import hashlib
import json

import httpx
import pytest
from PIL import Image

from models import Product, ProductImage
from services.product_media_url_backfill_download import (
    BoundedProductMediaDownloader,
    ProductMediaDownloadBlockedError,
)
from services.product_media_url_backfill_manifest import (
    ProductMediaUrlBackfillManifest,
    ProductMediaUrlBackfillManifestError,
    is_canonical_product_media_url,
)
from services.product_media_url_backfill_plan_token import (
    ProductMediaUrlBackfillBlockedError,
    ProductMediaUrlBackfillPlanToken,
)
from services.product_media_url_backfill_service import ProductMediaUrlBackfillService
from services.product_media_url_backfill_state import (
    LoadedProductMediaUrlState,
    detect_product_media_url_collisions,
)
from services.product_media_url_public_audit import ProductMediaUrlPublicAudit


def _manifest_payload(**overrides):
    payload = {
        "version": 1,
        "name": "test-media-repair",
        "public_catalog_url": "https://api.mvn.by/api/v1/products",
        "expected_public_product_count": 1,
        "expected_public_snapshot_sha256": "a" * 64,
        "expected_db_snapshot_sha256": "b" * 64,
        "sources": [
            {
                "old_url": "/media/products/legacy.webp",
                "action": "reuse",
                "expected_product_ids": [7],
                "target_url": "https://cdn.mvn.by/products/variants/original/legacy.webp",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_manifest_is_closed_deterministic_and_prevents_overlapping_products() -> None:
    first = ProductMediaUrlBackfillManifest.normalize(_manifest_payload())
    second = ProductMediaUrlBackfillManifest.normalize(_manifest_payload())
    assert first.fingerprint == second.fingerprint
    with pytest.raises(ProductMediaUrlBackfillManifestError, match="fields"):
        ProductMediaUrlBackfillManifest.normalize(
            {**_manifest_payload(), "allow_any_host": True}
        )
    duplicate = _manifest_payload()
    duplicate["sources"].append(
        {
            "old_url": "/media/products/other.webp",
            "action": "blocked",
            "expected_product_ids": [7],
            "blocked_reason": "review",
        }
    )
    with pytest.raises(ProductMediaUrlBackfillManifestError, match="only one"):
        ProductMediaUrlBackfillManifest.normalize(duplicate)


def test_external_ingest_requires_explicit_rights_and_host_boundary() -> None:
    payload = _manifest_payload(
        sources=[
            {
                "old_url": "https://vendor.example/image.jpg",
                "action": "ingest",
                "expected_product_ids": [7],
                "fetch_url": "https://vendor.example/image.jpg",
                "allowed_redirect_hosts": ["vendor.example"],
            }
        ]
    )
    with pytest.raises(ProductMediaUrlBackfillManifestError, match="rights_review_ref"):
        ProductMediaUrlBackfillManifest.normalize(payload)
    payload["sources"][0]["rights_review_ref"] = "license-ticket-123"
    assert ProductMediaUrlBackfillManifest.normalize(payload).sources[0].action == "ingest"


def test_collision_preflight_uses_resolved_ingest_target() -> None:
    old_url = "https://cdn.mvn.by/products/library/model.jpg"
    target_url = "https://cdn.mvn.by/products/shared/model.webp"
    manifest = ProductMediaUrlBackfillManifest.normalize(
        _manifest_payload(
            sources=[
                {
                    "old_url": old_url,
                    "action": "ingest",
                    "expected_product_ids": [7],
                    "fetch_url": old_url,
                    "allowed_redirect_hosts": ["cdn.mvn.by"],
                    "rights_review_ref": "mvn-owned-catalog-media",
                }
            ]
        )
    )
    old_image = ProductImage(id=10, product_id=7, url=old_url)
    target_image = ProductImage(id=11, product_id=7, url=target_url)
    product = Product(
        id=7,
        title="Model",
        slug="model",
        price=1,
        main_image=old_url,
        gallery_images=[old_image, target_image],
    )
    state = LoadedProductMediaUrlState(
        products=[product],
        products_by_id={7: product},
        image_by_id={10: old_image, 11: target_image},
        variant_by_id={},
    )
    blockers: list[str] = []

    detect_product_media_url_collisions(
        state,
        manifest,
        {old_url: target_url},
        blockers,
    )

    assert blockers == [
        f"product#7 already has ProductImage target {target_url}"
    ]


@pytest.mark.parametrize(
    ("value", "allowed"),
    [
        ("https://cdn.mvn.by/products/shared/hash.webp", True),
        ("https://cdn.mvn.by/products/variants/original/model.JPG", True),
        ("https://cdn.mvn.by/products/library/model.webp", False),
        ("https://CDN.mvn.by/products/shared/hash.webp", False),
        ("https://cdn.mvn.by:443/products/shared/hash.webp", False),
        ("/media/products/hash.webp", False),
    ],
)
def test_canonical_media_predicate_matches_polotsk_contract(value: str, allowed: bool) -> None:
    assert is_canonical_product_media_url(value) is allowed


def test_plan_token_is_expiring_tamper_evident_and_domain_scoped() -> None:
    token = ProductMediaUrlBackfillPlanToken.issue(
        plan_digest="c" * 64,
        now=1_000,
        nonce="d" * 32,
    )
    assert ProductMediaUrlBackfillPlanToken.verify(token, now=1_010).plan_digest == "c" * 64
    with pytest.raises(ProductMediaUrlBackfillBlockedError, match="signature"):
        ProductMediaUrlBackfillPlanToken.verify(token[:-1] + "A", now=1_010)
    with pytest.raises(ProductMediaUrlBackfillBlockedError, match="expired"):
        ProductMediaUrlBackfillPlanToken.verify(token, now=2_000)


def _png_bytes() -> bytes:
    from io import BytesIO

    output = BytesIO()
    Image.new("RGB", (4, 3), color=(10, 20, 30)).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_bounded_downloader_validates_type_size_image_and_dns(monkeypatch) -> None:
    content = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/png", "content-length": str(len(content))},
            content=content,
            request=request,
        )

    monkeypatch.setattr(
        BoundedProductMediaDownloader,
        "_resolve_addresses",
        staticmethod(lambda _host: {"8.8.8.8"}),
    )
    downloader = BoundedProductMediaDownloader(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    result = await downloader.download(
        "https://images.example/model.png",
        allowed_hosts=("images.example",),
    )
    assert result.content_hash == hashlib.sha256(content).hexdigest()
    assert (result.width, result.height) == (4, 3)
    with pytest.raises(ProductMediaDownloadBlockedError, match="boundary"):
        await downloader.download(
            "https://private.example/model.png",
            allowed_hosts=("images.example",),
        )
    await downloader._client.aclose()


@pytest.mark.asyncio
async def test_public_audit_paginates_and_hashes_exact_product_fields() -> None:
    products = [
        {
            "id": 2,
            "slug": "two",
            "main_image": "https://cdn.mvn.by/products/shared/two.webp",
            "card_image": "https://cdn.mvn.by/products/shared/two.webp",
            "full_image": "https://cdn.mvn.by/products/shared/two.webp",
        },
        {
            "id": 1,
            "slug": "one",
            "main_image": "/media/products/one.webp",
            "card_image": "/media/products/one.webp",
            "full_image": "/media/products/one.webp",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "items": [products[page - 1]],
                "meta": {"total": 2, "page": page, "limit": 100, "pages": 2},
            },
            request=request,
        )

    manifest = ProductMediaUrlBackfillManifest.normalize(
        _manifest_payload(expected_public_product_count=2)
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ProductMediaUrlPublicAudit.run(manifest, client=client)
    expected = sorted(products, key=lambda item: item["id"])
    expected_hash = hashlib.sha256(
        json.dumps(expected, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    assert result["product_count"] == 2
    assert result["snapshot_sha256"] == expected_hash
    assert result["blocked_product_count"] == 1
    assert result["blocked_field_count"] == 3


@pytest.mark.asyncio
async def test_post_execute_verifier_accepts_only_the_three_acknowledged_residuals() -> None:
    executable_ids = list(range(1, 44))
    deferred_ids = [44, 45, 46]
    lg_url = "https://www.lg.com/content/dam/review-required.jpg"
    manifest = ProductMediaUrlBackfillManifest.normalize(
        _manifest_payload(
            expected_public_product_count=46,
            sources=[
                {
                    "old_url": "/media/products/legacy.webp",
                    "action": "reuse",
                    "expected_product_ids": executable_ids,
                    "target_url": "https://cdn.mvn.by/products/variants/original/legacy.webp",
                },
                {
                    "old_url": lg_url,
                    "action": "blocked",
                    "expected_product_ids": deferred_ids,
                    "blocked_reason": "external_rights_review_required",
                },
            ],
        )
    )
    products = []
    for product_id in executable_ids:
        products.append(
            {
                "id": product_id,
                "slug": f"ready-{product_id}",
                "main_image": "https://cdn.mvn.by/products/variants/original/legacy.webp",
                "card_image": "https://cdn.mvn.by/products/variants/original/legacy.webp",
                "full_image": "https://cdn.mvn.by/products/variants/original/legacy.webp",
            }
        )
    for product_id in deferred_ids:
        products.append(
            {
                "id": product_id,
                "slug": f"deferred-{product_id}",
                "main_image": lg_url,
                "card_image": lg_url,
                "full_image": lg_url,
            }
        )

    def transport_for(items):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "items": items,
                    "meta": {"total": 46, "page": 1, "limit": 100, "pages": 1},
                },
                request=request,
            )

        return httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport_for(products)) as client:
        verified = await ProductMediaUrlBackfillService.verify_public_residual(
            manifest,
            public_client=client,
        )
    assert verified["verified"] is True
    assert verified["blocked_product_count"] == 3
    assert verified["blocked_field_count"] == 9

    unexpected = [dict(item) for item in products]
    unexpected[0]["main_image"] = "/media/products/unexpected.webp"
    async with httpx.AsyncClient(transport=transport_for(unexpected)) as client:
        rejected = await ProductMediaUrlBackfillService.verify_public_residual(
            manifest,
            public_client=client,
        )
    assert rejected["verified"] is False
    assert rejected["unexpected_or_missing_residuals"]
