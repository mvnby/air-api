"""Canonical media URL policy for the shared MVN master catalog.

Partner storefronts deliberately render only immutable master-catalog media.
Manager writes must therefore reject URLs that those storefronts would hide.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from urllib.parse import urlsplit


CANONICAL_MEDIA_ORIGIN = "https://cdn.mvn.by"
_PRODUCT_PATH = re.compile(
    r"^/products/(?:shared|variants/original)/"
    r"[a-z0-9][a-z0-9._-]{0,199}\.(?:avif|gif|jpe?g|png|webp)$",
    re.IGNORECASE,
)
_CONTENT_PATH = re.compile(
    r"^/library/original/[a-f0-9]{64}\.(?:avif|gif|jpe?g|png|svg|webp)$"
)
_LOCAL_PRODUCT_PATH = re.compile(
    r"^/media/products/(?:shared|variants/original)/"
    r"[a-z0-9][a-z0-9._-]{0,199}\.(?:avif|gif|jpe?g|png|webp)$",
    re.IGNORECASE,
)
_LOCAL_CONTENT_PATH = re.compile(
    r"^/media/library/original/[a-f0-9]{64}\.(?:avif|gif|jpe?g|png|svg|webp)$"
)


class CatalogMediaKind(StrEnum):
    PRODUCT = "product"
    CONTENT = "content"
    SERIES = "series"


class CatalogMediaPolicy:
    """Validate media references against the partner publication boundary."""

    @classmethod
    def is_allowed(cls, value: str | None, *, kind: CatalogMediaKind) -> bool:
        candidate = str(value or "").strip()
        if not candidate:
            return True

        if cls.is_allowed_cdn(candidate, kind=kind):
            return True
        return cls._matches_active_local_storage(candidate, kind=kind)

    @classmethod
    def is_allowed_cdn(cls, value: str | None, *, kind: CatalogMediaKind) -> bool:
        candidate = str(value or "").strip()
        return bool(candidate) and cls._matches_canonical_origin(candidate, kind=kind)

    @classmethod
    def require_allowed(
        cls,
        value: str | None,
        *,
        kind: CatalogMediaKind,
        field: str,
    ) -> str | None:
        candidate = str(value or "").strip() or None
        if cls.is_allowed(candidate, kind=kind):
            return candidate
        expected = {
            CatalogMediaKind.PRODUCT: "/products/shared/ или /products/variants/original/",
            CatalogMediaKind.CONTENT: "/library/original/<sha256> (SVG разрешён)",
            CatalogMediaKind.SERIES: (
                "/library/original/<sha256>, /products/shared/ "
                "или /products/variants/original/"
            ),
        }[kind]
        raise ValueError(
            f"{field}: изображение нужно сначала загрузить в медиатеку; "
            f"ожидается {CANONICAL_MEDIA_ORIGIN}{expected}"
        )

    @classmethod
    def require_many(
        cls,
        values: Iterable[str | None],
        *,
        kind: CatalogMediaKind,
        field: str,
    ) -> list[str]:
        result: list[str] = []
        for index, value in enumerate(values, start=1):
            candidate = cls.require_allowed(
                value,
                kind=kind,
                field=f"{field}[{index}]",
            )
            if candidate:
                result.append(candidate)
        return result

    @classmethod
    def require_series_blocks(
        cls,
        blocks: Iterable[Mapping[str, object]],
        *,
        field: str,
    ) -> None:
        for index, block in enumerate(blocks, start=1):
            cls.require_allowed(
                str(block.get("image_url") or "") or None,
                kind=CatalogMediaKind.SERIES,
                field=f"{field}[{index}].image_url",
            )
            cls.require_optional_content_reference(
                str(block.get("icon") or "") or None,
                field=f"{field}[{index}].icon",
            )

    @classmethod
    def require_optional_content_reference(
        cls,
        value: str | None,
        *,
        field: str,
    ) -> str | None:
        """Validate a URL-like icon while preserving semantic icon names."""

        candidate = str(value or "").strip() or None
        if candidate and (
            candidate.startswith(("http://", "https://", "/"))
            or "/" in candidate
            or candidate.lower().endswith(".svg")
        ):
            return cls.require_allowed(
                candidate,
                kind=CatalogMediaKind.CONTENT,
                field=field,
            )
        return candidate

    @staticmethod
    def _matches_canonical_origin(candidate: str, *, kind: CatalogMediaKind) -> bool:
        if not candidate.startswith(f"{CANONICAL_MEDIA_ORIGIN}/"):
            return False
        try:
            parsed = urlsplit(candidate)
            port = parsed.port
        except ValueError:
            return False
        if (
            parsed.scheme != "https"
            or parsed.hostname != "cdn.mvn.by"
            or parsed.username
            or parsed.password
            or port
            or parsed.query
            or parsed.fragment
            or f"{parsed.scheme}://{parsed.netloc}" != CANONICAL_MEDIA_ORIGIN
        ):
            return False
        return CatalogMediaPolicy._path_matches(parsed.path, kind=kind)

    @staticmethod
    def _path_matches(path: str, *, kind: CatalogMediaKind) -> bool:
        if kind == CatalogMediaKind.PRODUCT:
            return bool(_PRODUCT_PATH.fullmatch(path))
        if kind == CatalogMediaKind.CONTENT:
            return bool(_CONTENT_PATH.fullmatch(path))
        return bool(_PRODUCT_PATH.fullmatch(path) or _CONTENT_PATH.fullmatch(path))

    @staticmethod
    def _matches_active_local_storage(candidate: str, *, kind: CatalogMediaKind) -> bool:
        if urlsplit(candidate).scheme or "?" in candidate or "#" in candidate:
            return False
        content_local = (
            os.getenv("MEDIA_STORAGE_PROVIDER", "local").strip().lower() == "local"
            and bool(_LOCAL_CONTENT_PATH.fullmatch(candidate))
        )
        product_local = (
            os.getenv("PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER", "local").strip().lower()
            == "local"
            and bool(_LOCAL_PRODUCT_PATH.fullmatch(candidate))
        )
        if kind == CatalogMediaKind.CONTENT:
            return content_local
        if kind == CatalogMediaKind.PRODUCT:
            return product_local
        return content_local or product_local
