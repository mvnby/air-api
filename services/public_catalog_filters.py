"""Derived public selection filters which do not depend on legacy tags."""
from collections.abc import Iterable

QUIET_CATALOG_MAX_NOISE_DB = 25


def quiet_catalog_noise_limit(tag_slugs: Iterable[str] | None) -> int | None:
    if any(str(slug).strip().lower() == "noise-silent" for slug in (tag_slugs or [])):
        return QUIET_CATALOG_MAX_NOISE_DB
    return None
