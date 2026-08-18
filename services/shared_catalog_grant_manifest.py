from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$|^[a-z0-9]$")
_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,159}$")


class SharedCatalogGrantManifestError(ValueError):
    pass


@dataclass(frozen=True)
class SharedCatalogGrantManifest:
    version: int
    tenant_slug: str
    storefront_slug: str
    mode: str
    price_policy: str
    owner_type: str
    actor_username: str
    batch_size: int
    fingerprint: str

    @classmethod
    def normalize(cls, payload: Any) -> "SharedCatalogGrantManifest":
        if not isinstance(payload, dict) or set(payload) != {
            "version",
            "tenant_slug",
            "storefront_slug",
            "mode",
            "price_policy",
            "owner_type",
            "actor_username",
            "batch_size",
        }:
            raise SharedCatalogGrantManifestError(
                "Grant manifest has unknown or missing fields"
            )
        version = payload["version"]
        if isinstance(version, bool) or version != 1:
            raise SharedCatalogGrantManifestError("Grant manifest version must be 1")
        tenant_slug = cls._slug(payload["tenant_slug"], "tenant_slug")
        storefront_slug = cls._slug(payload["storefront_slug"], "storefront_slug")
        mode = str(payload["mode"] or "").strip()
        price_policy = str(payload["price_policy"] or "").strip()
        owner_type = str(payload["owner_type"] or "").strip()
        actor_username = str(payload["actor_username"] or "").strip()
        batch_size = payload["batch_size"]
        if mode != "all_published":
            raise SharedCatalogGrantManifestError(
                "Only the all_published grant mode is supported"
            )
        if price_policy != "inherit_master":
            raise SharedCatalogGrantManifestError(
                "Only the inherit_master price policy is supported"
            )
        if owner_type != "system":
            raise SharedCatalogGrantManifestError(
                "Shared catalog grants must be system-owned"
            )
        if not _ACTOR.fullmatch(actor_username):
            raise SharedCatalogGrantManifestError("actor_username is invalid")
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= 200
        ):
            raise SharedCatalogGrantManifestError(
                "batch_size must be an integer between 1 and 200"
            )
        canonical = {
            "actor_username": actor_username,
            "batch_size": batch_size,
            "mode": mode,
            "owner_type": owner_type,
            "price_policy": price_policy,
            "storefront_slug": storefront_slug,
            "tenant_slug": tenant_slug,
            "version": 1,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return cls(**canonical, fingerprint=fingerprint)

    @staticmethod
    def _slug(value: Any, field: str) -> str:
        normalized = str(value or "").strip().casefold()
        if not _SLUG.fullmatch(normalized):
            raise SharedCatalogGrantManifestError(f"{field} is invalid")
        return normalized


__all__ = [
    "SharedCatalogGrantManifest",
    "SharedCatalogGrantManifestError",
]
