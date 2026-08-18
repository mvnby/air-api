from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from services.storefront_context_service import StorefrontContextService


POSTGRESQL_INTEGER_MAX = 2_147_483_647
MAX_OFFERS = 100
MAX_ALLOWED_HOSTNAMES = 5

RESERVED_HOSTNAMES = frozenset(
    {
        "mvn.by",
        "www.mvn.by",
        "api.mvn.by",
        "dev.mvn.by",
        "admin.mvn.by",
        "manager.mvn.by",
        "bot.mvn.by",
        "cdn.mvn.by",
        "static.mvn.by",
        "media.mvn.by",
        "mail.mvn.by",
        "smtp.mvn.by",
        "imap.mvn.by",
        "pop.mvn.by",
        "autodiscover.mvn.by",
        "ns1.mvn.by",
        "ns2.mvn.by",
    }
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_LOCALE_PATTERN = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_SENSITIVE_KEY_MARKERS = (
    "password",
    "secret",
    "credential",
    "api_key",
    "token",
)


class StorefrontOnboardingManifestError(ValueError):
    """Raised when a reviewed onboarding manifest is not closed and safe."""


@dataclass(frozen=True)
class TenantOnboardingSpec:
    slug: str
    display_name: str
    kind: str
    is_system: bool
    lifecycle: str


@dataclass(frozen=True)
class StorefrontOnboardingSpec:
    slug: str
    display_name: str
    city: str | None
    default_locale: str
    currency: str
    is_default: bool

    def target(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "status": "draft",
        }


@dataclass(frozen=True)
class StorefrontOnboardingOfferSpec:
    product_id: int | None
    product_slug: str | None
    price: int
    old_price: int | None
    is_published: bool

    @property
    def reference(self) -> str:
        if self.product_id is not None:
            return f"id:{self.product_id}"
        return f"slug:{self.product_slug}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StorefrontOnboardingManifest:
    version: int
    tenant: TenantOnboardingSpec
    storefront: StorefrontOnboardingSpec
    allowed_hostnames: tuple[str, ...]
    offers: tuple[StorefrontOnboardingOfferSpec, ...]

    ROOT_KEYS = frozenset(
        {"version", "tenant", "storefront", "allowed_hostnames", "offers"}
    )
    TENANT_KEYS = frozenset(
        {"slug", "display_name", "kind", "is_system", "lifecycle"}
    )
    STOREFRONT_KEYS = frozenset(
        {
            "slug",
            "display_name",
            "city",
            "default_locale",
            "currency",
            "is_default",
        }
    )
    OFFER_KEYS = frozenset(
        {"product_id", "product_slug", "price", "old_price", "is_published"}
    )

    @property
    def actor_username(self) -> str:
        return (
            f"system:storefront-onboarding:{self.tenant.slug}:"
            f"{self.storefront.slug}"
        )

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tenant": asdict(self.tenant),
            "storefront": asdict(self.storefront),
            "allowed_hostnames": list(self.allowed_hostnames),
            "offers": [offer.to_dict() for offer in self.offers],
        }

    @classmethod
    def normalize(cls, payload: Mapping[str, Any]) -> StorefrontOnboardingManifest:
        if not isinstance(payload, Mapping):
            raise StorefrontOnboardingManifestError("Manifest must be a JSON object")
        cls._reject_sensitive_keys(payload)
        cls._require_exact_keys(payload, cls.ROOT_KEYS, context="manifest")
        version = payload["version"]
        if isinstance(version, bool) or version != 1:
            raise StorefrontOnboardingManifestError("Manifest version must be 1")
        tenant = cls._normalize_tenant(payload["tenant"])
        storefront = cls._normalize_storefront(payload["storefront"])
        hostnames = cls._normalize_hostnames(payload["allowed_hostnames"])
        offers = cls._normalize_offers(payload["offers"])
        return cls(
            version=1,
            tenant=tenant,
            storefront=storefront,
            allowed_hostnames=hostnames,
            offers=offers,
        )

    def normalize_selected_hostname(self, hostname: str) -> str:
        normalized = self._normalize_hostname(hostname)
        if normalized not in self.allowed_hostnames:
            raise StorefrontOnboardingManifestError(
                "Hostname is not in the manifest's exact allowlist"
            )
        return normalized

    @classmethod
    def _normalize_tenant(cls, value: Any) -> TenantOnboardingSpec:
        cls._require_mapping(value, context="tenant")
        cls._require_exact_keys(value, cls.TENANT_KEYS, context="tenant")
        slug = cls._slug(value["slug"], field="tenant.slug")
        display_name = cls._text(
            value["display_name"], field="tenant.display_name", max_length=160
        )
        kind = str(value["kind"] or "").strip()
        if kind not in {"operator", "independent_seller"}:
            raise StorefrontOnboardingManifestError(
                "tenant.kind must be operator or independent_seller"
            )
        is_system = value["is_system"]
        if not isinstance(is_system, bool):
            raise StorefrontOnboardingManifestError("tenant.is_system must be boolean")
        lifecycle = str(value["lifecycle"] or "").strip()
        if lifecycle not in {"existing", "managed"}:
            raise StorefrontOnboardingManifestError(
                "tenant.lifecycle must be existing or managed"
            )
        if lifecycle == "managed" and (is_system or kind != "independent_seller"):
            raise StorefrontOnboardingManifestError(
                "Managed tenants must be non-system independent sellers"
            )
        return TenantOnboardingSpec(
            slug=slug,
            display_name=display_name,
            kind=kind,
            is_system=is_system,
            lifecycle=lifecycle,
        )

    @classmethod
    def _normalize_storefront(cls, value: Any) -> StorefrontOnboardingSpec:
        cls._require_mapping(value, context="storefront")
        cls._require_exact_keys(value, cls.STOREFRONT_KEYS, context="storefront")
        city_value = value["city"]
        city = (
            None
            if city_value is None
            else cls._text(city_value, field="storefront.city", max_length=120)
        )
        locale = str(value["default_locale"] or "").strip()
        if not _LOCALE_PATTERN.fullmatch(locale):
            raise StorefrontOnboardingManifestError(
                "storefront.default_locale must look like ru-BY"
            )
        currency = str(value["currency"] or "").strip()
        if not _CURRENCY_PATTERN.fullmatch(currency):
            raise StorefrontOnboardingManifestError(
                "storefront.currency must be an uppercase ISO-style code"
            )
        is_default = value["is_default"]
        if not isinstance(is_default, bool):
            raise StorefrontOnboardingManifestError(
                "storefront.is_default must be boolean"
            )
        return StorefrontOnboardingSpec(
            slug=cls._slug(value["slug"], field="storefront.slug"),
            display_name=cls._text(
                value["display_name"],
                field="storefront.display_name",
                max_length=160,
            ),
            city=city,
            default_locale=locale,
            currency=currency,
            is_default=is_default,
        )

    @classmethod
    def _normalize_hostnames(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise StorefrontOnboardingManifestError(
                "allowed_hostnames must be an array"
            )
        if not 1 <= len(value) <= MAX_ALLOWED_HOSTNAMES:
            raise StorefrontOnboardingManifestError(
                f"allowed_hostnames must contain between 1 and {MAX_ALLOWED_HOSTNAMES} hosts"
            )
        normalized = tuple(cls._normalize_hostname(item) for item in value)
        if len(normalized) != len(set(normalized)):
            raise StorefrontOnboardingManifestError(
                "allowed_hostnames contains duplicates after normalization"
            )
        return tuple(sorted(normalized))

    @staticmethod
    def _normalize_hostname(value: Any) -> str:
        raw = str(value or "").strip()
        if ":" in raw:
            raise StorefrontOnboardingManifestError(
                "Storefront hostname must not include a port"
            )
        try:
            normalized = StorefrontContextService.normalize_hostname(raw)
        except ValueError as exc:
            raise StorefrontOnboardingManifestError(str(exc)) from exc
        if "." not in normalized:
            raise StorefrontOnboardingManifestError(
                "Storefront hostname must be a fully qualified domain"
            )
        if normalized in RESERVED_HOSTNAMES:
            raise StorefrontOnboardingManifestError(
                "Storefront hostname is reserved and cannot be onboarded"
            )
        return normalized

    @classmethod
    def _normalize_offers(
        cls, value: Any
    ) -> tuple[StorefrontOnboardingOfferSpec, ...]:
        if not isinstance(value, list):
            raise StorefrontOnboardingManifestError("offers must be an array")
        if len(value) > MAX_OFFERS:
            raise StorefrontOnboardingManifestError(
                f"offers must contain at most {MAX_OFFERS} items"
            )
        offers = tuple(cls._normalize_offer(item) for item in value)
        references = [offer.reference for offer in offers]
        if len(references) != len(set(references)):
            raise StorefrontOnboardingManifestError(
                "offers contains duplicate product references"
            )
        return tuple(sorted(offers, key=lambda offer: offer.reference))

    @classmethod
    def _normalize_offer(cls, value: Any) -> StorefrontOnboardingOfferSpec:
        cls._require_mapping(value, context="offer")
        supplied = set(value)
        required = {"price", "old_price", "is_published"}
        unknown = sorted(supplied - cls.OFFER_KEYS)
        missing = sorted(required - supplied)
        if missing or unknown:
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if unknown:
                details.append("unknown fields: " + ", ".join(unknown))
            raise StorefrontOnboardingManifestError(
                "offer must use the closed schema (" + "; ".join(details) + ")"
            )
        raw_product_id = value.get("product_id")
        raw_product_slug = value.get("product_slug")
        if (raw_product_id is None) == (raw_product_slug is None):
            raise StorefrontOnboardingManifestError(
                "Each offer must contain exactly one product reference"
            )
        product_id = (
            None
            if raw_product_id is None
            else cls._positive_int(raw_product_id, field="offer.product_id")
        )
        product_slug = (
            None
            if raw_product_slug is None
            else cls._slug(raw_product_slug, field="offer.product_slug", max_length=255)
        )
        price = cls._non_negative_int(value["price"], field="offer.price")
        old_price = (
            None
            if value["old_price"] is None
            else cls._non_negative_int(value["old_price"], field="offer.old_price")
        )
        if old_price is not None and old_price < price:
            raise StorefrontOnboardingManifestError(
                "offer.old_price must be greater than or equal to price"
            )
        is_published = value["is_published"]
        if not isinstance(is_published, bool):
            raise StorefrontOnboardingManifestError(
                "offer.is_published must be true or false"
            )
        return StorefrontOnboardingOfferSpec(
            product_id=product_id,
            product_slug=product_slug,
            price=price,
            old_price=old_price,
            is_published=is_published,
        )

    @staticmethod
    def _require_mapping(value: Any, *, context: str) -> None:
        if not isinstance(value, Mapping):
            raise StorefrontOnboardingManifestError(f"{context} must be an object")

    @staticmethod
    def _require_exact_keys(
        value: Mapping[str, Any], allowed: frozenset[str], *, context: str
    ) -> None:
        supplied = set(value)
        missing = sorted(allowed - supplied)
        unknown = sorted(supplied - allowed)
        if missing or unknown:
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if unknown:
                details.append("unknown: " + ", ".join(unknown))
            raise StorefrontOnboardingManifestError(
                f"{context} must use the exact closed schema ({'; '.join(details)})"
            )

    @classmethod
    def _reject_sensitive_keys(cls, value: Any, *, path: str = "manifest") -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized = str(key).casefold()
                if any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS):
                    raise StorefrontOnboardingManifestError(
                        f"Secrets and passwords are forbidden in manifests ({path}.{key})"
                    )
                cls._reject_sensitive_keys(nested, path=f"{path}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                cls._reject_sensitive_keys(nested, path=f"{path}[{index}]")

    @staticmethod
    def _text(value: Any, *, field: str, max_length: int) -> str:
        normalized = str(value or "").strip()
        if not normalized or len(normalized) > max_length or any(
            ord(character) < 32 for character in normalized
        ):
            raise StorefrontOnboardingManifestError(f"{field} is invalid")
        return normalized

    @staticmethod
    def _slug(value: Any, *, field: str, max_length: int = 64) -> str:
        normalized = str(value or "").strip()
        if len(normalized) > max_length or not _SLUG_PATTERN.fullmatch(normalized):
            raise StorefrontOnboardingManifestError(f"{field} is invalid")
        return normalized

    @classmethod
    def _positive_int(cls, value: Any, *, field: str) -> int:
        normalized = cls._bounded_int(value, field=field)
        if normalized <= 0:
            raise StorefrontOnboardingManifestError(f"{field} must be positive")
        return normalized

    @classmethod
    def _non_negative_int(cls, value: Any, *, field: str) -> int:
        normalized = cls._bounded_int(value, field=field)
        if normalized < 0:
            raise StorefrontOnboardingManifestError(
                f"{field} must be non-negative"
            )
        return normalized

    @staticmethod
    def _bounded_int(value: Any, *, field: str) -> int:
        if isinstance(value, bool):
            raise StorefrontOnboardingManifestError(f"{field} must be an integer")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise StorefrontOnboardingManifestError(
                f"{field} must be an integer"
            ) from exc
        if str(value).strip() != str(normalized):
            raise StorefrontOnboardingManifestError(
                f"{field} must be an exact integer"
            )
        if normalized > POSTGRESQL_INTEGER_MAX:
            raise StorefrontOnboardingManifestError(
                f"{field} exceeds the PostgreSQL integer range"
            )
        return normalized


__all__ = [
    "MAX_ALLOWED_HOSTNAMES",
    "MAX_OFFERS",
    "RESERVED_HOSTNAMES",
    "StorefrontOnboardingManifest",
    "StorefrontOnboardingManifestError",
    "StorefrontOnboardingOfferSpec",
    "StorefrontOnboardingSpec",
    "TenantOnboardingSpec",
]
