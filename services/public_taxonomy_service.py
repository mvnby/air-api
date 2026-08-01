"""Pure public taxonomy visibility rules used by response mapping."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class PublicTaxonomyService:
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
