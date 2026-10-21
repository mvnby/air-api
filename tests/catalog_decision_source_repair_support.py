"""Synthetic states for the real, bounded issue-1190 manifest (no supplier prices)."""

from copy import deepcopy
from types import SimpleNamespace as NS

from services.catalog_decision_source_repair import load_manifest, product_identity, product_projection
from services.catalog_decision_data_repair import digest


def prepared_catalog():
    manifest, products, commerce = deepcopy(load_manifest()), [], {}
    for row in manifest["products"]:
        before = row["before"]
        pid = row["identity"]["id"]
        product = NS(
            **{key: value for key, value in row["identity"].items() if key != "source_url_sha256"},
            source_url=f"https://example.invalid/products/{pid}",
            **{key: before[key] for key in ("product_kind", "power_cooling", "is_inverter", "is_published", "catalog_category_override", "series_assignment_source")},
            price=1234, old_price=None,
            specs={"type": "полупромышленный кондиционер", "capacity_cooling_kw": "7", "indoor_type": "канальный", "untouched": [1, {"raw": "keep"}]},
            tags=[NS(slug="cat-industrial")], brand=NS(slug=before["brand_slug"]),
            series=NS(slug=before["series_slug"]) if before["series_slug"] else None,
        )
        commerce[pid] = {"mappings": [], "sources": [], "local_stocks": []}
        products.append(product)
        row["identity"] = product_identity(product)
        row["before"] = product_projection(product, commerce[pid])
        row["before_sha256"] = digest(row["before"])
    return manifest, products, commerce


def pin_fixture(monkeypatch, manifest):
    import services.catalog_decision_source_repair as policy
    monkeypatch.setattr(policy, "REVIEWED_MANIFEST_SHA256", digest(manifest))
