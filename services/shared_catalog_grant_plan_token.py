from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass

from core.config import settings
from services.shared_catalog_grant_planner import SharedCatalogGrantBlockedError


_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class VerifiedSharedCatalogGrantPlanToken:
    plan_digest: str
    issued_at: int
    nonce: str


class SharedCatalogGrantPlanToken:
    VERSION = 1
    MAX_AGE_SECONDS = 15 * 60
    FUTURE_SKEW_SECONDS = 30

    @classmethod
    def issue(
        cls,
        *,
        plan_digest: str,
        now: int | None = None,
        nonce: str | None = None,
    ) -> str:
        if not _DIGEST_PATTERN.fullmatch(str(plan_digest or "")):
            raise ValueError("Plan digest must be a SHA-256 digest")
        payload = {
            "v": cls.VERSION,
            "iat": int(time.time() if now is None else now),
            "nonce": nonce or secrets.token_hex(16),
            "digest": plan_digest,
        }
        if not _NONCE_PATTERN.fullmatch(str(payload["nonce"])):
            raise ValueError("Plan token nonce is invalid")
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(cls._key(), encoded, hashlib.sha256).digest()
        return f"{cls._b64encode(encoded)}.{cls._b64encode(signature)}"

    @classmethod
    def verify(
        cls,
        token: str,
        *,
        now: int | None = None,
    ) -> VerifiedSharedCatalogGrantPlanToken:
        normalized = str(token or "").strip()
        if len(normalized) > 512 or normalized.count(".") != 1:
            raise SharedCatalogGrantBlockedError(
                "Execute requires the exact token from a fresh plan"
            )
        encoded_part, signature_part = normalized.split(".", 1)
        try:
            encoded = cls._b64decode(encoded_part)
            signature = cls._b64decode(signature_part)
        except ValueError as exc:
            raise SharedCatalogGrantBlockedError("Plan token is malformed") from exc
        expected = hmac.new(cls._key(), encoded, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise SharedCatalogGrantBlockedError(
                "Plan token signature is invalid"
            )
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SharedCatalogGrantBlockedError(
                "Plan token payload is invalid"
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "iat",
            "nonce",
            "digest",
        }:
            raise SharedCatalogGrantBlockedError("Plan token payload is invalid")
        issued_at = payload["iat"]
        if (
            payload["v"] != cls.VERSION
            or isinstance(payload["v"], bool)
            or isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or not _NONCE_PATTERN.fullmatch(str(payload["nonce"]))
            or not _DIGEST_PATTERN.fullmatch(str(payload["digest"]))
        ):
            raise SharedCatalogGrantBlockedError("Plan token payload is invalid")
        current = int(time.time() if now is None else now)
        if issued_at > current + cls.FUTURE_SKEW_SECONDS:
            raise SharedCatalogGrantBlockedError("Plan token was issued in the future")
        if current - issued_at > cls.MAX_AGE_SECONDS:
            raise SharedCatalogGrantBlockedError(
                "Plan token expired; run a fresh plan"
            )
        return VerifiedSharedCatalogGrantPlanToken(
            plan_digest=str(payload["digest"]),
            issued_at=issued_at,
            nonce=str(payload["nonce"]),
        )

    @staticmethod
    def _key() -> bytes:
        return hashlib.sha256(
            b"mvn:shared-catalog-grant:plan-token:v1\0"
            + settings.SECRET_KEY.encode("utf-8")
        ).digest()

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        try:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("invalid base64url") from exc


__all__ = ["SharedCatalogGrantPlanToken"]
