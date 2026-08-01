from __future__ import annotations

import hmac
from collections.abc import Iterable
from dataclasses import dataclass, field

from core.public_write_key import (
    normalize_public_write_idempotency_key,
    public_write_idempotency_key_sha256,
)
from core.storefront_request_envelope import storefront_signing_header_state
from services.storefront_context_service import StorefrontContextService
from services.storefront_context_signature_service import (
    InvalidStorefrontContextSignature,
    StorefrontContextSignatureService,
)


STOREFRONT_VERIFIED_ENVELOPE_SCOPE_KEY = "mvn.storefront_verified_envelope"
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True, slots=True)
class StorefrontEnvelopeAuthConfig:
    primary_key_id: str
    primary_secret: str = field(repr=False)
    previous_key_id: str = ""
    previous_secret: str = field(default="", repr=False)
    allowed_api_hosts: tuple[str, ...] = ()
    max_age_seconds: int = 300


@dataclass(frozen=True, slots=True)
class VerifiedStorefrontEnvelope:
    hostname: str


def _decode_ascii_header(value: bytes, *, label: str) -> str:
    try:
        return value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise InvalidStorefrontContextSignature(
            f"Storefront context {label} is invalid"
        ) from exc


def _complete_signing_headers(
    raw_headers: tuple[tuple[bytes, bytes], ...],
) -> dict[bytes, bytes]:
    has_storefront_headers, complete = storefront_signing_header_state(raw_headers)
    if not has_storefront_headers or not complete:
        raise InvalidStorefrontContextSignature(
            "Storefront context signing headers are incomplete"
        )
    return {
        name.lower(): value
        for name, value in raw_headers
        if name.lower().startswith(b"x-mvn-storefront-")
    }


def _select_signing_secret(
    *,
    supplied_key_id: str,
    config: StorefrontEnvelopeAuthConfig,
) -> str:
    if not config.primary_key_id or not config.primary_secret:
        raise InvalidStorefrontContextSignature(
            "Storefront context signing is disabled"
        )
    if bool(config.previous_key_id) != bool(config.previous_secret):
        raise InvalidStorefrontContextSignature(
            "Storefront context signing keyring is invalid"
        )

    candidates = [(config.primary_key_id, config.primary_secret)]
    if config.previous_key_id and config.previous_secret:
        if config.previous_key_id == config.primary_key_id:
            raise InvalidStorefrontContextSignature(
                "Storefront context signing keyring is invalid"
            )
        candidates.append((config.previous_key_id, config.previous_secret))

    selected = ""
    supplied = supplied_key_id.encode("utf-8")
    for candidate_id, candidate_secret in candidates:
        if hmac.compare_digest(candidate_id.encode("utf-8"), supplied):
            selected = candidate_secret
    if not selected:
        raise InvalidStorefrontContextSignature(
            "Storefront context signing key is not allowed"
        )
    return selected


def resolve_allowed_api_hostname(
    *,
    raw_headers: Iterable[tuple[bytes, bytes]],
    allowed_api_hosts: Iterable[str],
) -> str:
    headers = tuple(raw_headers)
    host_values = [value for name, value in headers if name.lower() == b"host"]
    if len(host_values) != 1:
        raise InvalidStorefrontContextSignature(
            "Storefront context API host is invalid"
        )
    raw_hostname = _decode_ascii_header(host_values[0], label="API host")
    try:
        hostname = StorefrontContextService.normalize_hostname(raw_hostname)
        allowed = {
            StorefrontContextService.normalize_hostname(item)
            for item in allowed_api_hosts
        }
    except (TypeError, ValueError) as exc:
        raise InvalidStorefrontContextSignature(
            "Storefront context API host allowlist is invalid"
        ) from exc
    if hostname not in allowed:
        raise InvalidStorefrontContextSignature(
            "Storefront context API host is not allowed"
        )
    return hostname


def resolve_idempotency_key_binding(
    *,
    raw_headers: Iterable[tuple[bytes, bytes]],
    method: str,
    required_for_write: bool,
) -> str:
    """Return the signed digest, rejecting ambiguous header representations."""

    values = [
        value
        for name, value in raw_headers
        if name.lower() == b"idempotency-key"
    ]
    is_read = str(method or "").upper() in _READ_METHODS
    if is_read:
        if values:
            raise InvalidStorefrontContextSignature(
                "Storefront context idempotency key is invalid"
            )
        return ""
    if not values:
        if required_for_write:
            raise InvalidStorefrontContextSignature(
                "Storefront context idempotency key is required"
            )
        return ""
    if len(values) != 1:
        raise InvalidStorefrontContextSignature(
            "Storefront context idempotency key is invalid"
        )
    raw_value = _decode_ascii_header(values[0], label="idempotency key")
    try:
        normalized = normalize_public_write_idempotency_key(raw_value)
    except ValueError as exc:
        raise InvalidStorefrontContextSignature(
            "Storefront context idempotency key is invalid"
        ) from exc
    if raw_value != normalized:
        raise InvalidStorefrontContextSignature(
            "Storefront context idempotency key is not canonical"
        )
    return public_write_idempotency_key_sha256(normalized)


def authenticate_storefront_envelope(
    *,
    raw_headers: Iterable[tuple[bytes, bytes]],
    method: str,
    raw_path: bytes,
    query_string: bytes,
    body_sha256: str,
    config: StorefrontEnvelopeAuthConfig,
) -> VerifiedStorefrontEnvelope:
    """Verify one complete request envelope without parsing its body."""

    headers = tuple(raw_headers)
    signing_headers = _complete_signing_headers(headers)
    key_id = _decode_ascii_header(
        signing_headers[b"x-mvn-storefront-key-id"],
        label="key ID",
    )
    storefront_hostname = _decode_ascii_header(
        signing_headers[b"x-mvn-storefront-host"],
        label="storefront host",
    )
    raw_timestamp = _decode_ascii_header(
        signing_headers[b"x-mvn-storefront-timestamp"],
        label="timestamp",
    )
    signature = _decode_ascii_header(
        signing_headers[b"x-mvn-storefront-signature"],
        label="signature",
    )
    if not raw_timestamp.isdigit() or (
        raw_timestamp != "0" and raw_timestamp.startswith("0")
    ):
        raise InvalidStorefrontContextSignature(
            "Storefront context timestamp is not canonical"
        )

    api_hostname = resolve_allowed_api_hostname(
        raw_headers=headers,
        allowed_api_hosts=config.allowed_api_hosts,
    )
    secret = _select_signing_secret(
        supplied_key_id=key_id,
        config=config,
    )
    target = StorefrontContextSignatureService.request_target(
        raw_path=raw_path,
        query_string=query_string,
    )
    idempotency_key_sha256 = resolve_idempotency_key_binding(
        raw_headers=headers,
        method=method,
        required_for_write=True,
    )
    hostname = StorefrontContextSignatureService.verify(
        secret=secret,
        timestamp=int(raw_timestamp),
        method=method,
        path_and_query=target,
        api_hostname=api_hostname,
        storefront_hostname=storefront_hostname,
        body_sha256=body_sha256,
        idempotency_key_sha256=idempotency_key_sha256,
        signature=signature,
        max_age_seconds=config.max_age_seconds,
    )
    return VerifiedStorefrontEnvelope(hostname=hostname)
