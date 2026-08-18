from __future__ import annotations

import hmac
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit

from services.storefront_context_service import StorefrontContextService


_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ROLES = frozenset({"primary", "previous"})
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_KEYS = 64


class InvalidStorefrontSigningKeyring(ValueError):
    """Raised for an unsafe runtime keyring without exposing secret input."""


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StorefrontSigningKey:
    key_id: str
    secret: str = field(repr=False)
    host_roles: tuple[tuple[str, str], ...]
    legacy_v1_read_compatible: bool = False

    def role_for(self, hostname: str) -> str | None:
        for allowed_hostname, role in self.host_roles:
            if allowed_hostname == hostname:
                return role
        return None


@dataclass(frozen=True, slots=True)
class StorefrontSigningKeyring:
    keys: tuple[StorefrontSigningKey, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.keys)

    def has_primary_for(self, hostname: str) -> bool:
        return any(key.role_for(hostname) == "primary" for key in self.keys)


def is_valid_storefront_signing_key_id(value: str) -> bool:
    return bool(_KEY_ID_PATTERN.fullmatch(str(value or "")))


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _normalize_key_id(value: object) -> str:
    if not isinstance(value, str) or not is_valid_storefront_signing_key_id(value):
        raise InvalidStorefrontSigningKeyring("invalid key ID")
    return value


def _normalize_secret(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidStorefrontSigningKeyring("invalid secret")
    size = len(value.encode("utf-8"))
    if size < 32 or size > 4096:
        raise InvalidStorefrontSigningKeyring("invalid secret length")
    return value


def _normalize_exact_hostname(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidStorefrontSigningKeyring("invalid storefront hostname")
    try:
        normalized = StorefrontContextService.normalize_hostname(value)
    except (TypeError, ValueError) as exc:
        raise InvalidStorefrontSigningKeyring(
            "invalid storefront hostname"
        ) from exc
    if value != normalized:
        raise InvalidStorefrontSigningKeyring(
            "storefront hostname must already be canonical"
        )
    return normalized


def _parse_json_keys(raw_json: str) -> list[StorefrontSigningKey]:
    if not raw_json:
        return []
    if len(raw_json.encode("utf-8")) > _MAX_CONFIG_BYTES:
        raise InvalidStorefrontSigningKeyring("keyring JSON is too large")
    try:
        payload = json.loads(
            raw_json,
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (json.JSONDecodeError, _DuplicateJsonKey) as exc:
        raise InvalidStorefrontSigningKeyring("keyring JSON is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"keys"}:
        raise InvalidStorefrontSigningKeyring(
            "keyring JSON must contain only the keys object"
        )
    raw_keys = payload["keys"]
    if not isinstance(raw_keys, dict) or not raw_keys:
        raise InvalidStorefrontSigningKeyring("keys must be a non-empty object")
    if len(raw_keys) > _MAX_KEYS:
        raise InvalidStorefrontSigningKeyring("too many signing keys")

    parsed: list[StorefrontSigningKey] = []
    for raw_key_id, raw_entry in raw_keys.items():
        key_id = _normalize_key_id(raw_key_id)
        if not isinstance(raw_entry, dict) or set(raw_entry) != {
            "secret",
            "host_roles",
        }:
            raise InvalidStorefrontSigningKeyring(
                "each key must contain only secret and host_roles"
            )
        secret = _normalize_secret(raw_entry["secret"])
        raw_host_roles = raw_entry["host_roles"]
        if not isinstance(raw_host_roles, dict) or len(raw_host_roles) != 1:
            raise InvalidStorefrontSigningKeyring(
                "each signing key must bind exactly one storefront host"
            )
        host_roles: list[tuple[str, str]] = []
        for raw_hostname, raw_role in raw_host_roles.items():
            hostname = _normalize_exact_hostname(raw_hostname)
            if not isinstance(raw_role, str) or raw_role not in _ROLES:
                raise InvalidStorefrontSigningKeyring("invalid host key role")
            host_roles.append((hostname, raw_role))
        parsed.append(
            StorefrontSigningKey(
                key_id=key_id,
                secret=secret,
                host_roles=tuple(sorted(host_roles)),
            )
        )
    return parsed


def canonical_public_site_hostname(public_site_url: str) -> str:
    try:
        parsed = urlsplit(str(public_site_url or "").strip())
        explicit_port = parsed.port
    except ValueError as exc:
        raise InvalidStorefrontSigningKeyring(
            "PUBLIC_SITE_URL is invalid"
        ) from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise InvalidStorefrontSigningKeyring("PUBLIC_SITE_URL is invalid")
    if (
        parsed.username is not None
        or parsed.password is not None
        or explicit_port is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise InvalidStorefrontSigningKeyring("PUBLIC_SITE_URL is invalid")
    try:
        return StorefrontContextService.normalize_hostname(parsed.hostname)
    except (TypeError, ValueError) as exc:
        raise InvalidStorefrontSigningKeyring(
            "PUBLIC_SITE_URL is invalid"
        ) from exc


def _parse_legacy_hosts(raw_hosts: str, *, public_site_url: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in raw_hosts.split(",") if item.strip())
    if not values:
        raise InvalidStorefrontSigningKeyring(
            "legacy keys require an explicit canonical host allowlist"
        )
    canonical_hostname = canonical_public_site_hostname(public_site_url)
    normalized = tuple(_normalize_exact_hostname(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise InvalidStorefrontSigningKeyring("legacy host allowlist is duplicated")
    if set(normalized) != {canonical_hostname}:
        raise InvalidStorefrontSigningKeyring(
            "legacy keys may be bound only to the canonical PUBLIC_SITE_URL host"
        )
    return normalized


def _append_legacy_keys(
    keys: list[StorefrontSigningKey],
    *,
    primary_key_id: str,
    primary_secret: str,
    previous_key_id: str,
    previous_secret: str,
    legacy_allowed_hosts: str,
    public_site_url: str,
) -> None:
    any_legacy_value = any(
        (primary_key_id, primary_secret, previous_key_id, previous_secret)
    )
    if not any_legacy_value:
        if legacy_allowed_hosts.strip():
            raise InvalidStorefrontSigningKeyring(
                "legacy host allowlist requires a legacy signing key"
            )
        return
    if bool(primary_key_id) != bool(primary_secret):
        raise InvalidStorefrontSigningKeyring(
            "legacy primary key pair is incomplete"
        )
    if bool(previous_key_id) != bool(previous_secret):
        raise InvalidStorefrontSigningKeyring(
            "legacy previous key pair is incomplete"
        )
    if previous_key_id and not primary_key_id:
        raise InvalidStorefrontSigningKeyring(
            "legacy previous key requires a primary key"
        )
    primary_id = _normalize_key_id(primary_key_id)
    primary_value = _normalize_secret(primary_secret)
    if previous_key_id and previous_key_id == primary_id:
        raise InvalidStorefrontSigningKeyring(
            "legacy primary and previous key IDs must differ"
        )
    hosts = _parse_legacy_hosts(
        legacy_allowed_hosts,
        public_site_url=public_site_url,
    )
    keys.append(
        StorefrontSigningKey(
            key_id=primary_id,
            secret=primary_value,
            host_roles=tuple((hostname, "primary") for hostname in hosts),
            legacy_v1_read_compatible=True,
        )
    )
    if previous_key_id:
        previous_id = _normalize_key_id(previous_key_id)
        previous_value = _normalize_secret(previous_secret)
        keys.append(
            StorefrontSigningKey(
                key_id=previous_id,
                secret=previous_value,
                host_roles=tuple((hostname, "previous") for hostname in hosts),
                legacy_v1_read_compatible=True,
            )
        )


def _validate_rotation(keys: list[StorefrontSigningKey]) -> None:
    if len(keys) > _MAX_KEYS:
        raise InvalidStorefrontSigningKeyring("too many signing keys")
    key_ids = [key.key_id for key in keys]
    if len(set(key_ids)) != len(key_ids):
        raise InvalidStorefrontSigningKeyring("signing key IDs must be unique")
    for index, key in enumerate(keys):
        for other in keys[index + 1 :]:
            if hmac.compare_digest(
                key.secret.encode("utf-8"),
                other.secret.encode("utf-8"),
            ):
                raise InvalidStorefrontSigningKeyring(
                    "signing secrets must be unique across key IDs"
                )

    roles_by_host: dict[str, dict[str, str]] = {}
    for key in keys:
        for hostname, role in key.host_roles:
            host_roles = roles_by_host.setdefault(hostname, {})
            if role in host_roles:
                raise InvalidStorefrontSigningKeyring(
                    f"storefront host has more than one {role} key"
                )
            host_roles[role] = key.key_id
    for host_roles in roles_by_host.values():
        if "primary" not in host_roles:
            raise InvalidStorefrontSigningKeyring(
                "a previous key requires a primary key for the same host"
            )


@lru_cache(maxsize=16)
def build_storefront_signing_keyring(
    *,
    raw_json: str,
    legacy_primary_key_id: str,
    legacy_primary_secret: str,
    legacy_previous_key_id: str,
    legacy_previous_secret: str,
    legacy_allowed_hosts: str,
    public_site_url: str,
) -> StorefrontSigningKeyring:
    """Build and validate the immutable runtime keyring from secret settings."""

    keys = _parse_json_keys(str(raw_json or ""))
    _append_legacy_keys(
        keys,
        primary_key_id=str(legacy_primary_key_id or ""),
        primary_secret=str(legacy_primary_secret or ""),
        previous_key_id=str(legacy_previous_key_id or ""),
        previous_secret=str(legacy_previous_secret or ""),
        legacy_allowed_hosts=str(legacy_allowed_hosts or ""),
        public_site_url=public_site_url,
    )
    _validate_rotation(keys)
    return StorefrontSigningKeyring(keys=tuple(keys))
