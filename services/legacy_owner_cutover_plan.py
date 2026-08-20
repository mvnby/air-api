"""Signed, short-lived plan tokens for legacy-owner state transitions."""

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


_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class VerifiedLegacyOwnerPlanToken:
    plan_digest: str
    issued_at: int
    nonce: str


class LegacyOwnerPlanToken:
    VERSION = 1
    MAX_AGE_SECONDS = 15 * 60
    FUTURE_SKEW_SECONDS = 30

    @classmethod
    def issue(cls, *, plan_digest: str, now: int | None = None) -> str:
        if not _DIGEST_PATTERN.fullmatch(str(plan_digest or "")):
            raise ValueError("Plan digest is invalid")
        payload = {
            "v": cls.VERSION,
            "iat": int(time.time() if now is None else now),
            "nonce": secrets.token_hex(16),
            "digest": plan_digest,
        }
        encoded = cls._encode(payload)
        signature = hmac.new(cls._key(), encoded, hashlib.sha256).digest()
        return f"{cls._b64encode(encoded)}.{cls._b64encode(signature)}"

    @classmethod
    def verify(
        cls,
        token: str,
        *,
        now: int | None = None,
    ) -> VerifiedLegacyOwnerPlanToken:
        normalized = str(token or "").strip()
        if len(normalized) > 512 or normalized.count(".") != 1:
            raise ValueError("Execute requires the exact token from a fresh plan")
        encoded_part, signature_part = normalized.split(".", 1)
        try:
            encoded = cls._b64decode(encoded_part)
            signature = cls._b64decode(signature_part)
        except ValueError as exc:
            raise ValueError("Plan token is malformed") from exc
        expected = hmac.new(cls._key(), encoded, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Plan token signature is invalid")
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Plan token payload is invalid") from exc
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "iat",
            "nonce",
            "digest",
        }:
            raise ValueError("Plan token payload is invalid")
        version = payload["v"]
        issued_at = payload["iat"]
        nonce = str(payload["nonce"])
        digest = str(payload["digest"])
        if version != cls.VERSION or isinstance(version, bool):
            raise ValueError("Plan token version is unsupported")
        if isinstance(issued_at, bool) or not isinstance(issued_at, int):
            raise ValueError("Plan token timestamp is invalid")
        if not _NONCE_PATTERN.fullmatch(nonce) or not _DIGEST_PATTERN.fullmatch(digest):
            raise ValueError("Plan token payload is invalid")
        current = int(time.time() if now is None else now)
        if issued_at > current + cls.FUTURE_SKEW_SECONDS:
            raise ValueError("Plan token was issued in the future")
        if current - issued_at > cls.MAX_AGE_SECONDS:
            raise ValueError("Plan token expired; run a fresh plan")
        return VerifiedLegacyOwnerPlanToken(digest, issued_at, nonce)

    @staticmethod
    def _encode(payload: dict[str, object]) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        try:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("invalid base64url") from exc

    @staticmethod
    def _key() -> bytes:
        return hashlib.sha256(
            b"mvn:legacy-owner-cutover:plan-token:v1\0"
            + settings.SECRET_KEY.encode("utf-8")
        ).digest()


__all__ = ["LegacyOwnerPlanToken", "VerifiedLegacyOwnerPlanToken"]
