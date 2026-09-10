from __future__ import annotations

import base64
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass

from core.config import settings
from core.integration_credential_keyring import IntegrationCredentialUnavailable


_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SIGNING_CONTEXT = b"mvn.integration-credential-rewrap.plan-token.v1"


class IntegrationCredentialRotationBlockedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedIntegrationCredentialRotationToken:
    plan_digest: str
    issued_at: int


class IntegrationCredentialRotationToken:
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
            raise IntegrationCredentialRotationBlockedError(
                "Plan digest must be SHA-256"
            )
        payload = {
            "v": cls.VERSION,
            "iat": int(time.time() if now is None else now),
            "nonce": nonce or secrets.token_hex(16),
            "digest": plan_digest,
        }
        if not _NONCE_PATTERN.fullmatch(str(payload["nonce"])):
            raise IntegrationCredentialRotationBlockedError("Plan token is invalid")
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"{cls._b64encode(encoded)}.{cls._signature(encoded)}"

    @classmethod
    def verify(
        cls,
        token: str,
        *,
        now: int | None = None,
    ) -> VerifiedIntegrationCredentialRotationToken:
        normalized = str(token or "").strip()
        if len(normalized) > 512 or normalized.count(".") != 1:
            raise IntegrationCredentialRotationBlockedError(
                "Execute requires the exact token from a fresh plan"
            )
        encoded_part, signature = normalized.split(".", 1)
        if not re.fullmatch(r"[0-9a-f]{64}", signature):
            raise IntegrationCredentialRotationBlockedError(
                "Plan token signature is invalid"
            )
        try:
            encoded = cls._b64decode(encoded_part)
            expected = cls._signature(encoded)
        except (ValueError, IntegrationCredentialUnavailable) as exc:
            raise IntegrationCredentialRotationBlockedError(
                "Plan token cannot be verified"
            ) from exc
        if not hmac.compare_digest(signature, expected):
            raise IntegrationCredentialRotationBlockedError(
                "Plan token signature is invalid"
            )
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise IntegrationCredentialRotationBlockedError(
                "Plan token payload is invalid"
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "iat",
            "nonce",
            "digest",
        }:
            raise IntegrationCredentialRotationBlockedError(
                "Plan token payload is invalid"
            )
        issued_at = payload["iat"]
        if (
            payload["v"] != cls.VERSION
            or isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or not _NONCE_PATTERN.fullmatch(str(payload["nonce"]))
            or not _DIGEST_PATTERN.fullmatch(str(payload["digest"]))
        ):
            raise IntegrationCredentialRotationBlockedError(
                "Plan token payload is invalid"
            )
        current = int(time.time() if now is None else now)
        if issued_at > current + cls.FUTURE_SKEW_SECONDS:
            raise IntegrationCredentialRotationBlockedError(
                "Plan token was issued in the future"
            )
        if current - issued_at > cls.MAX_AGE_SECONDS:
            raise IntegrationCredentialRotationBlockedError(
                "Plan token expired; run a fresh plan"
            )
        return VerifiedIntegrationCredentialRotationToken(
            plan_digest=str(payload["digest"]),
            issued_at=issued_at,
        )

    @staticmethod
    def _signature(encoded: bytes) -> str:
        keyring = settings.integration_credential_keyring
        if not keyring.enabled or keyring.write_mode != "active":
            raise IntegrationCredentialUnavailable(
                "Integration credential active key is unavailable"
            )
        return keyring.fingerprint(encoded, context=_SIGNING_CONTEXT)

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("invalid base64url")
        try:
            decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("invalid base64url") from exc
        if IntegrationCredentialRotationToken._b64encode(decoded) != value:
            raise ValueError("invalid base64url")
        return decoded


__all__ = [
    "IntegrationCredentialRotationBlockedError",
    "IntegrationCredentialRotationToken",
]
