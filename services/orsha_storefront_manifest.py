from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


POSTGRESQL_INTEGER_MAX = 2_147_483_647


class OrshaStorefrontManifestError(ValueError):
    """Raised when the reviewed Orsha offer allowlist is malformed."""


@dataclass(frozen=True)
class OrshaStorefrontOfferSpec:
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


class OrshaStorefrontManifest:
    MIN_OFFERS = 5
    MAX_OFFERS = 20
    ALLOWED_KEYS = frozenset(
        {
            "product_id",
            "product_slug",
            "price",
            "old_price",
            "is_published",
        }
    )

    @classmethod
    def normalize(
        cls,
        values: Iterable[Mapping[str, Any]],
    ) -> tuple[OrshaStorefrontOfferSpec, ...]:
        offers = tuple(cls._normalize_one(value) for value in values)
        if not cls.MIN_OFFERS <= len(offers) <= cls.MAX_OFFERS:
            raise OrshaStorefrontManifestError(
                f"Orsha allowlist must contain between {cls.MIN_OFFERS} and "
                f"{cls.MAX_OFFERS} offers"
            )

        references = [offer.reference for offer in offers]
        if len(references) != len(set(references)):
            raise OrshaStorefrontManifestError(
                "Orsha allowlist contains duplicate product references"
            )
        return tuple(sorted(offers, key=lambda offer: offer.reference))

    @classmethod
    def _normalize_one(
        cls,
        value: Mapping[str, Any],
    ) -> OrshaStorefrontOfferSpec:
        if not isinstance(value, Mapping):
            raise OrshaStorefrontManifestError("Each offer must be an object")
        unknown = sorted(set(value) - cls.ALLOWED_KEYS)
        if unknown:
            raise OrshaStorefrontManifestError(
                "Offer contains unknown fields: " + ", ".join(unknown)
            )

        raw_product_id = value.get("product_id")
        raw_product_slug = value.get("product_slug")
        has_product_id = raw_product_id is not None
        has_product_slug = raw_product_slug is not None
        if has_product_id == has_product_slug:
            raise OrshaStorefrontManifestError(
                "Each offer must contain exactly one of product_id or product_slug"
            )

        product_id = None
        product_slug = None
        if has_product_id:
            product_id = cls._positive_int(raw_product_id, field="product_id")
        else:
            product_slug = str(raw_product_slug or "").strip()
            if (
                not product_slug
                or len(product_slug) > 255
                or any(character.isspace() for character in product_slug)
                or any(character in product_slug for character in "/?#\\")
            ):
                raise OrshaStorefrontManifestError("product_slug is invalid")

        price = cls._non_negative_int(value.get("price"), field="price")
        raw_old_price = value.get("old_price")
        old_price = (
            None
            if raw_old_price is None
            else cls._non_negative_int(raw_old_price, field="old_price")
        )
        if old_price is not None and old_price < price:
            raise OrshaStorefrontManifestError(
                "old_price must be greater than or equal to price"
            )
        is_published = value.get("is_published")
        if not isinstance(is_published, bool):
            raise OrshaStorefrontManifestError("is_published must be true or false")

        return OrshaStorefrontOfferSpec(
            product_id=product_id,
            product_slug=product_slug,
            price=price,
            old_price=old_price,
            is_published=is_published,
        )

    @staticmethod
    def _positive_int(value: Any, *, field: str) -> int:
        normalized = OrshaStorefrontManifest._bounded_int(value, field=field)
        if normalized <= 0:
            raise OrshaStorefrontManifestError(f"{field} must be positive")
        return normalized

    @staticmethod
    def _non_negative_int(value: Any, *, field: str) -> int:
        normalized = OrshaStorefrontManifest._bounded_int(value, field=field)
        if normalized < 0:
            raise OrshaStorefrontManifestError(f"{field} must be non-negative")
        return normalized

    @staticmethod
    def _bounded_int(value: Any, *, field: str) -> int:
        if isinstance(value, bool):
            raise OrshaStorefrontManifestError(f"{field} must be an integer")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise OrshaStorefrontManifestError(
                f"{field} must be an integer"
            ) from exc
        if str(value).strip() != str(normalized):
            raise OrshaStorefrontManifestError(f"{field} must be an exact integer")
        if normalized > POSTGRESQL_INTEGER_MAX:
            raise OrshaStorefrontManifestError(
                f"{field} exceeds the PostgreSQL integer range"
            )
        return normalized
