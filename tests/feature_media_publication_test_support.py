"""Synthetic media references; no production snapshots or local asset paths."""

from types import SimpleNamespace

from services.feature_media_publication import FEATURE_IDS, IMAGE_IDS, digest


def publication_fixture():
    rows, features, assets = [], [], []
    for id in sorted(FEATURE_IDS):
        identity = {"id": id, "slug": f"feature-{id}",
            "scope_type": "derived" if id in {40, 73, 84} else "universal", "brand_id": None}
        before = {"icon": "legacy-icon-preserved", "icon_media_id": None,
            "image_url": "https://old.example/retained.jpg", "image_media_id": None}
        target = {}
        for kind, offset in (("icon", 10000), ("image", 20000)):
            if kind == "image" and id not in IMAGE_IDS:
                continue
            hash = digest(f"{kind}-{id}")
            reference = {"id": offset + id, "url": f"/media/library/original/{hash}.svg",
                "content_hash": hash}
            target[kind] = reference
            assets.append(SimpleNamespace(**reference, kind="feature", processing_status="ready",
                variant_type="original", parent_asset_id=None, tenant_id=None,
                storefront_id=None, mime_type="image/svg+xml", storage_provider="local"))
        rows.append({"identity": identity, "before": before, "target": target})
        features.append(SimpleNamespace(**identity, **before, name="Preserve name",
            short_description="Preserve prose", sort_order=17, is_active=True,
            archived_at=None, category_id=1))
    return {"schema_version": 1, "features": rows}, features, assets
