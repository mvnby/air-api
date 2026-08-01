from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from crud.tenancy import TenancyDAO


_HOST_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class InvalidStorefrontHostError(ValueError):
    pass


@dataclass(frozen=True)
class StorefrontContext:
    tenant_id: int
    tenant_slug: str
    tenant_kind: str
    storefront_id: int
    storefront_slug: str
    storefront_name: str
    hostname: str
    city: str | None
    default_locale: str
    currency: str
    tenant_is_system: bool = False


class StorefrontContextService:
    @staticmethod
    def normalize_hostname(raw_host: str) -> str:
        value = str(raw_host or "").strip()
        if not value or len(value) > 320:
            raise InvalidStorefrontHostError("Storefront host is missing or too long")
        if "://" in value or any(char in value for char in "/?#@,\\"):
            raise InvalidStorefrontHostError("Storefront host must contain only a hostname and optional port")
        if any(ord(char) < 33 or ord(char) == 127 for char in value):
            raise InvalidStorefrontHostError("Storefront host contains invalid characters")

        try:
            parsed = urlsplit(f"//{value}")
            hostname = (parsed.hostname or "").rstrip(".").lower()
            parsed.port
        except ValueError as exc:
            raise InvalidStorefrontHostError("Storefront host contains an invalid port") from exc
        if value.endswith(":"):
            raise InvalidStorefrontHostError("Storefront host contains an invalid port")

        if not hostname:
            raise InvalidStorefrontHostError("Storefront hostname is missing")

        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise InvalidStorefrontHostError("Storefront hostname is not a valid IDNA domain") from exc

        if len(ascii_hostname) > 253:
            raise InvalidStorefrontHostError("Storefront hostname is too long")
        labels = ascii_hostname.split(".")
        if any(not _HOST_LABEL_PATTERN.fullmatch(label) for label in labels):
            raise InvalidStorefrontHostError("Storefront hostname contains an invalid label")
        return ascii_hostname

    @classmethod
    async def resolve_by_host(
        cls,
        session: AsyncSession,
        raw_host: str,
    ) -> StorefrontContext | None:
        hostname = cls.normalize_hostname(raw_host)
        row = await TenancyDAO.get_active_storefront_by_hostname(session, hostname)
        if row is None:
            return None
        return StorefrontContext(**asdict(row))

    @classmethod
    async def resolve_by_scope(
        cls,
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
    ) -> StorefrontContext | None:
        row = await TenancyDAO.get_active_storefront_by_scope(
            session,
            tenant_id=tenant_id,
            storefront_id=storefront_id,
        )
        if row is None:
            return None
        return StorefrontContext(**asdict(row))
