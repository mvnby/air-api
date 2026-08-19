"""Short-lived signed token for an exact reviewed media backfill plan."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")


class ProductMediaUrlBackfillBlockedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedProductMediaUrlBackfillPlanToken:
    plan_digest: str
    issued_at: int
    nonce: str


class ProductMediaUrlBackfillPlanToken:
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
        if not _DIGEST_RE.fullmatch(str(plan_digest or "")):
            raise ValueError("Plan digest must be SHA-256")
        payload = {
            "v": cls.VERSION,
            "iat": int(time.time() if now is None else now),
            "nonce": nonce or secrets.token_hex(16),
            "digest": plan_digest,
        }
        if not _NONCE_RE.fullmatch(str(payload["nonce"])):
            raise ValueError("Plan nonce is invalid")
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(cls._key(), encoded, hashlib.sha256).digest()
        return f"{cls._encode(encoded)}.{cls._encode(signature)}"

    @classmethod
    def verify(
        cls,
        token: str,
        *,
        now: int | None = None,
    ) -> VerifiedProductMediaUrlBackfillPlanToken:
        value = str(token or "").strip()
        if len(value) > 512 or value.count(".") != 1:
            raise ProductMediaUrlBackfillBlockedError(
                "Execute requires the exact token from a fresh plan"
            )
        payload_part, signature_part = value.split(".", 1)
        try:
            encoded = cls._decode(payload_part)
            signature = cls._decode(signature_part)
        except ValueError as exc:
            raise ProductMediaUrlBackfillBlockedError("Plan token is malformed") from exc
        expected = hmac.new(cls._key(), encoded, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ProductMediaUrlBackfillBlockedError(
                "Plan token signature is invalid"
            )
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProductMediaUrlBackfillBlockedError(
                "Plan token payload is invalid"
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {"v", "iat", "nonce", "digest"}:
            raise ProductMediaUrlBackfillBlockedError("Plan token payload is invalid")
        issued_at = payload["iat"]
        if (
            payload["v"] != cls.VERSION
            or isinstance(payload["v"], bool)
            or isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or not _NONCE_RE.fullmatch(str(payload["nonce"]))
            or not _DIGEST_RE.fullmatch(str(payload["digest"]))
        ):
            raise ProductMediaUrlBackfillBlockedError("Plan token payload is invalid")
        current = int(time.time() if now is None else now)
        if issued_at > current + cls.FUTURE_SKEW_SECONDS:
            raise ProductMediaUrlBackfillBlockedError("Plan token is from the future")
        if current - issued_at > cls.MAX_AGE_SECONDS:
            raise ProductMediaUrlBackfillBlockedError(
                "Plan token expired; run a fresh plan"
            )
        return VerifiedProductMediaUrlBackfillPlanToken(
            plan_digest=str(payload["digest"]),
            issued_at=issued_at,
            nonce=str(payload["nonce"]),
        )

    @staticmethod
    def _key() -> bytes:
        from core.config import settings

        return hashlib.sha256(
            b"mvn:product-media-url-backfill:plan-token:v1\0"
            + settings.SECRET_KEY.encode("utf-8")
        ).digest()

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        try:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("invalid base64url") from exc


__all__ = [
    "ProductMediaUrlBackfillBlockedError",
    "ProductMediaUrlBackfillPlanToken",
    "VerifiedProductMediaUrlBackfillPlanToken",
]
