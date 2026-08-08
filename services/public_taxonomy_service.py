"""Pure public taxonomy visibility rules used by response mapping."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class PublicTaxonomyService:
    @staticmethod
    def public_brand(product: Any) -> Any | None:
        """Return the eagerly loaded brand only when it is public."""
        brand = getattr(product, "__dict__", {}).get("brand")
        if brand is None or getattr(brand, "is_published", False) is not True:
            return None
        return brand

    @staticmethod
    def public_series(product: Any) -> Any | None:
        """Return the eagerly loaded series only when it is public."""
        series = getattr(product, "__dict__", {}).get("series")
        if series is None or getattr(series, "is_published", False) is not True:
            return None
        return series

    @staticmethod
    def is_public_tag(tag: Any) -> bool:
        group = getattr(tag, "group", None)
        return bool(
            getattr(tag, "is_public", False) is True
            and group is not None
            and getattr(group, "is_public", False) is True
        )

    @staticmethod
    def visible_tags(tags: Iterable[Any] | None) -> list[Any]:
        return [
            tag
            for tag in (tags or [])
            if PublicTaxonomyService.is_public_tag(tag)
        ]
