"""Synthetic commercial states with the exact reviewed public field deltas."""

from copy import deepcopy

from services.catalog_decision_data_repair import digest
from services.catalog_decision_price_repair import apply_operation, load_manifest
from services.catalog_decision_source_repair import product_identity, product_projection
from tests.catalog_decision_source_repair_support import prepared_catalog as source_catalog


def reset_technical_before(product, row):
    specs = deepcopy(product.specs)
    for patch in row["patches"]:
        if patch["path"] == "power_cooling":
            product.power_cooling = patch["before"]
            continue
        parts, target = patch["path"].split(".")[1:], specs
        for key in parts[:-1]:
            target = target.setdefault(key, {})
        if patch["before_exists"]:
            target[parts[-1]] = deepcopy(patch["before"])
        else:
            target.pop(parts[-1], None)
    product.specs = specs


def refresh_guards(row, product, commerce):
    row["identity"] = product_identity(product)
    row["before"] = product_projection(product, commerce)
    target = deepcopy(product)
    apply_operation(target, row)
    row["target"] = product_projection(target, commerce)
    row["before_sha256"], row["target_sha256"] = digest(row["before"]), digest(row["target"])


def prepared_catalog():
    manifest = deepcopy(load_manifest())
    _, products, commerce = source_catalog()
    by_id = {p.id: p for p in products}
    for row in manifest["products"]:
        product = by_id[row["identity"]["id"]]
        reset_technical_before(product, row)
        refresh_guards(row, product, commerce[product.id])
    return manifest, products, commerce


def pin_fixture(monkeypatch, manifest):
    import services.catalog_decision_price_repair as policy
    monkeypatch.setattr(policy, "REVIEWED_MANIFEST_SHA256", digest(manifest))
