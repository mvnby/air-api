from __future__ import annotations

import hmac
import re
import time
from hashlib import sha256

from services.storefront_context_service import StorefrontContextService


_BODY_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE_PATTERN = re.compile(r"^v1=[0-9a-f]{64}$")
_HTTP_METHOD_PATTERN = re.compile(r"^[A-Z][A-Z0-9!#$%&'*+.^_`|~-]*$")


class InvalidStorefrontContextSignature(ValueError):
    pass


class StorefrontContextSignatureService:
    """Create and verify the trusted storefront request envelope."""

    VERSION = "v1"
    EMPTY_BODY_SHA256 = sha256(b"").hexdigest()

    @staticmethod
    def body_sha256(body: bytes) -> str:
        return sha256(bytes(body)).hexdigest()

    @staticmethod
    def request_target(*, raw_path: bytes, query_string: bytes = b"") -> bytes:
        path = bytes(raw_path)
        query = bytes(query_string)
        if not path.startswith(b"/") or b"\r" in path or b"\n" in path:
            raise InvalidStorefrontContextSignature(
                "Storefront context request path is invalid"
            )
        if b"\r" in query or b"\n" in query or b"#" in query:
            raise InvalidStorefrontContextSignature(
                "Storefront context query string is invalid"
            )
        return path + (b"?" + query if query else b"")

    @classmethod
    def canonical_message(
        cls,
        *,
        timestamp: int,
        method: str,
        path_and_query: str | bytes,
        api_hostname: str,
        storefront_hostname: str,
        body_sha256: str,
    ) -> bytes:
        normalized_method = str(method or "").strip().upper()
        if not _HTTP_METHOD_PATTERN.fullmatch(normalized_method):
            raise InvalidStorefrontContextSignature(
                "Storefront context HTTP method is invalid"
            )

        if isinstance(path_and_query, bytes):
            target = bytes(path_and_query)
        else:
            target = str(path_and_query or "").encode("utf-8")
        if not target.startswith(b"/") or b"\r" in target or b"\n" in target:
            raise InvalidStorefrontContextSignature(
                "Storefront context request target is invalid"
            )

        normalized_api_hostname = StorefrontContextService.normalize_hostname(
            api_hostname
        )
        normalized_storefront_hostname = (
            StorefrontContextService.normalize_hostname(storefront_hostname)
        )
        normalized_body_sha256 = str(body_sha256 or "")
        if not _BODY_SHA256_PATTERN.fullmatch(normalized_body_sha256):
            raise InvalidStorefrontContextSignature(
                "Storefront context body digest is invalid"
            )

        return b"\n".join(
            (
                cls.VERSION.encode("ascii"),
                str(int(timestamp)).encode("ascii"),
                normalized_method.encode("ascii"),
                target,
                normalized_api_hostname.encode("ascii"),
                normalized_storefront_hostname.encode("ascii"),
                normalized_body_sha256.encode("ascii"),
            )
        )

    @classmethod
    def sign(
        cls,
        *,
        secret: str,
        timestamp: int,
        method: str,
        path_and_query: str | bytes,
        api_hostname: str,
        storefront_hostname: str,
        body_sha256: str,
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
                path_and_query=path_and_query,
                api_hostname=api_hostname,
                storefront_hostname=storefront_hostname,
                body_sha256=body_sha256,
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
        path_and_query: str | bytes,
        api_hostname: str,
        storefront_hostname: str,
        body_sha256: str,
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

        normalized_signature = str(signature or "")
        if not _SIGNATURE_PATTERN.fullmatch(normalized_signature):
            raise InvalidStorefrontContextSignature(
                "Storefront context signature is invalid"
            )
        normalized_storefront_hostname = (
            StorefrontContextService.normalize_hostname(storefront_hostname)
        )
        expected = cls.sign(
            secret=normalized_secret,
            timestamp=signed_timestamp,
            method=method,
            path_and_query=path_and_query,
            api_hostname=api_hostname,
            storefront_hostname=normalized_storefront_hostname,
            body_sha256=body_sha256,
        )
        if not hmac.compare_digest(expected, normalized_signature):
            raise InvalidStorefrontContextSignature(
                "Storefront context signature is invalid"
            )
        return normalized_storefront_hostname
