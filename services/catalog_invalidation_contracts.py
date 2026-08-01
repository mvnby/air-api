from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT = (
    "catalog.cache_invalidation.requested.v1"
)
CATALOG_INVALIDATION_SCHEMA_VERSION = 1
_CACHE_KEY_PATTERN = re.compile(r"^g(?P<global>\d+)-s(?P<storefront>\d+)$")
_REASON_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")


class CatalogCacheInvalidationRequestedV1(BaseModel):
    """Immutable cache invalidation input for one exact storefront."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = CATALOG_INVALIDATION_SCHEMA_VERSION
    scope: Literal["global", "storefront"]
    tenant_id: int = Field(gt=0)
    storefront_id: int = Field(gt=0)
    origins: list[str] = Field(max_length=50)
    paths: list[str] = Field(min_length=1)
    global_revision: int = Field(ge=0)
    storefront_revision: int = Field(ge=0)
    cache_key: str = Field(min_length=5, max_length=80)
    reason: str = Field(min_length=1, max_length=120)

    @field_validator("origins")
    @classmethod
    def _validate_origins(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_value in values:
            value = str(raw_value or "").strip().rstrip("/")
            parsed = urlsplit(value)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError(
                    "Catalog invalidation origin is invalid"
                ) from exc
            if (
                parsed.scheme.casefold() not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Catalog invalidation origin is invalid")
            hostname = parsed.hostname.casefold().rstrip(".")
            if not hostname or any(character.isspace() for character in hostname):
                raise ValueError("Catalog invalidation origin is invalid")
            if ":" in hostname:
                hostname = f"[{hostname}]"
            default_port = (
                parsed.scheme.casefold() == "https" and port == 443
            ) or (parsed.scheme.casefold() == "http" and port == 80)
            netloc = hostname if port is None or default_port else f"{hostname}:{port}"
            normalized.append(
                urlunsplit(
                    (parsed.scheme.casefold(), netloc, "", "", "")
                )
            )
        return sorted(set(normalized), key=str.casefold)

    @field_validator("paths")
    @classmethod
    def _validate_paths(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_value in values:
            value = str(raw_value or "").strip()
            if (
                not value.startswith("/")
                or len(value) > 2048
                or "?" in value
                or "#" in value
                or "://" in value
                or "\\" in value
                or any(ord(character) < 32 for character in value)
            ):
                raise ValueError("Catalog invalidation path is invalid")
            normalized.append(value)
        deduped = sorted(set(normalized))
        if not deduped:
            raise ValueError("Catalog invalidation paths cannot be empty")
        return deduped

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not _REASON_PATTERN.fullmatch(normalized):
            raise ValueError("Catalog invalidation reason is invalid")
        return normalized

    @model_validator(mode="after")
    def _validate_cache_key(self):
        match = _CACHE_KEY_PATTERN.fullmatch(self.cache_key)
        if match is None or (
            int(match.group("global")) != self.global_revision
            or int(match.group("storefront")) != self.storefront_revision
        ):
            raise ValueError("Catalog invalidation cache key is inconsistent")
        return self


def catalog_cache_key(*, global_revision: int, storefront_revision: int) -> str:
    return f"g{max(0, int(global_revision))}-s{max(0, int(storefront_revision))}"
