"""Public identity from canonical catalog specs; no title or power inference."""

from typing import Any

from services.spec_registry import canonical_capacity_class


def public_product_identity(specs: Any) -> dict[str, str | None]:
    specs = specs if isinstance(specs, dict) else {}
    model = specs.get("model")
    model_code = (model.strip() or None) if isinstance(model, str) else None
    return {
        "model_code": model_code,
        "capacity_class": canonical_capacity_class(specs.get("capacity_class")),
    }
