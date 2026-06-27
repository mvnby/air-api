from __future__ import annotations

from typing import Any, Mapping, Sequence

from services.spec_normalizer import normalize_specs


INTERNAL_SPEC_KEYS = (
    "__typed_specs",
    "__filter_min_heat",
    "__filter_wifi",
    "__filter_wifi_builtin",
    "__filter_noise_min",
    "__filter_indoor_type",
    "compressor_type_norm",
)


def build_specs_with_typed_internal_layer(
    specs: Mapping[str, Any] | None,
    *,
    wifi_tag_slugs: Sequence[str] | None = None,
    strict_wifi_from_tags: bool = False,
    title: str = "",
) -> dict[str, Any]:
    """Return specs with refreshed internal typed/filter keys only.

    The regular normalizer may also rename public flat keys. For a safe legacy
    backfill we want only the machine-readable internal layer so existing
    storefront/admin displays keep their current flat values.
    """

    original = dict(specs or {})
    normalized = normalize_specs(
        original,
        keep_units=True,
        wifi_tag_slugs=wifi_tag_slugs,
        strict_wifi_from_tags=strict_wifi_from_tags,
        title=title,
    )
    updated = dict(original)
    for key in INTERNAL_SPEC_KEYS:
        if key in normalized:
            updated[key] = normalized[key]
        else:
            updated.pop(key, None)
    return updated

