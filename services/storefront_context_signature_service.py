from __future__ import annotations

import hmac
import time
from hashlib import sha256
from typing import Iterable

from services.storefront_context_service import StorefrontContextService


class InvalidStorefrontContextSignature(ValueError):
    pass


class StorefrontContextSignatureService:
    """Sign the storefront hostname selected by a trusted website runtime."""

    VERSION = "v1"

    @classmethod
    def canonical_message(
        cls,
        *,
        timestamp: int,
        method: str,
        path: str,
        hostname: str,
    ) -> bytes:
        normalized_hostname = StorefrontContextService.normalize_hostname(hostname)
        normalized_method = str(method or "").strip().upper()
        normalized_path = str(path or "").strip()
        if not normalized_method or not normalized_path.startswith("/"):
            raise InvalidStorefrontContextSignature(
                "Storefront context request target is invalid"
            )
        return (
            f"{cls.VERSION}\n{int(timestamp)}\n{normalized_method}\n"
            f"{normalized_path}\n{normalized_hostname}"
        ).encode("utf-8")

    @classmethod
    def sign(
        cls,
        *,
        secret: str,
        timestamp: int,
        method: str,
        path: str,
        hostname: str,
    ) -> str:
        normalized_secret = str(secret or "")
        if len(normalized_secret.encode("utf-8")) < 32:
            raise InvalidStorefrontContextSignature(
                "Storefront context signing secret is not configured securely"
            )
        digest = hmac.new(
            normalized_secret.encode("utf-8"),
            cls.canonical_message(
                timestamp=timestamp,
                method=method,
                path=path,
                hostname=hostname,
            ),
            sha256,
        ).hexdigest()
        return f"{cls.VERSION}={digest}"

    @classmethod
    def verify(
        cls,
        *,
        secret: str,
        timestamp: int,
        method: str,
        path: str,
        hostname: str,
        signature: str,
        max_age_seconds: int,
        now: int | None = None,
    ) -> str:
        normalized_secret = str(secret or "")
        if len(normalized_secret.encode("utf-8")) < 32:
            raise InvalidStorefrontContextSignature(
                "Storefront context signing secret is not configured securely"
            )

        max_age = int(max_age_seconds)
        if max_age <= 0:
            raise InvalidStorefrontContextSignature(
                "Storefront context signature lifetime is invalid"
            )
        current_timestamp = int(time.time()) if now is None else int(now)
        signed_timestamp = int(timestamp)
        if abs(current_timestamp - signed_timestamp) > max_age:
            raise InvalidStorefrontContextSignature(
                "Storefront context signature has expired"
            )

        normalized_hostname = StorefrontContextService.normalize_hostname(hostname)
        expected = cls.sign(
            secret=normalized_secret,
            timestamp=signed_timestamp,
            method=method,
            path=path,
            hostname=normalized_hostname,
        )
        if not hmac.compare_digest(expected, str(signature or "")):
            raise InvalidStorefrontContextSignature(
                "Storefront context signature is invalid"
            )
        return normalized_hostname

    @classmethod
    def verify_any(
        cls,
        *,
        secrets: Iterable[str],
        timestamp: int,
        method: str,
        path: str,
        hostname: str,
        signature: str,
        max_age_seconds: int,
        now: int | None = None,
    ) -> str:
        configured = [str(secret or "") for secret in secrets if str(secret or "")]
        if not configured:
            raise InvalidStorefrontContextSignature(
                "Storefront context signing secret is not configured securely"
            )

        for secret in configured:
            try:
                return cls.verify(
                    secret=secret,
                    timestamp=timestamp,
                    method=method,
                    path=path,
                    hostname=hostname,
                    signature=signature,
                    max_age_seconds=max_age_seconds,
                    now=now,
                )
            except InvalidStorefrontContextSignature:
                continue
        raise InvalidStorefrontContextSignature(
            "Storefront context signature is invalid"
        )
