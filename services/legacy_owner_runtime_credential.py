"""Load and bind the retained runtime credential without exposing it."""

from __future__ import annotations

import hashlib
import hmac
import re

from core.config import settings
from services.legacy_owner_cutover_types import LegacyOwnerRuntimeIdentity
from services.staff_user_service import StaffUserService


class LegacyOwnerRuntimeCredential:
    @classmethod
    def load(cls) -> LegacyOwnerRuntimeIdentity:
        normalized_name = StaffUserService.normalize_username(settings.ADMIN_USERNAME)
        credential = str(settings.ADMIN_PASSWORD or "")
        local_binding = hmac.new(
            hashlib.sha256(
                b"mvn:legacy-owner-cutover:local-plan-binding:v1\0"
                + settings.SECRET_KEY.encode("utf-8")
            ).digest(),
            (str(normalized_name or "") + "\0" + credential).encode(
                "utf-8", errors="surrogatepass"
            ),
            hashlib.sha256,
        ).hexdigest()
        return LegacyOwnerRuntimeIdentity(
            normalized_name=normalized_name,
            credential=credential,
            identity_canonical=str(settings.ADMIN_USERNAME or "") == normalized_name,
            binding=local_binding,
        )

    @staticmethod
    def bind(
        runtime: LegacyOwnerRuntimeIdentity,
        *,
        challenge: str,
    ) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", challenge):
            raise ValueError("Runtime credential binding challenge is invalid")
        return hmac.new(
            hashlib.sha256(
                b"mvn:legacy-owner-cutover:runtime-binding:v2\0"
                + bytes.fromhex(challenge)
            ).digest(),
            (str(runtime.normalized_name or "") + "\0" + runtime.credential).encode(
                "utf-8", errors="surrogatepass"
            ),
            hashlib.sha256,
        ).hexdigest()


__all__ = ["LegacyOwnerRuntimeCredential"]
