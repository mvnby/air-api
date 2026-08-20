"""Load and bind the retained runtime credential without exposing it."""

from __future__ import annotations

import hashlib
import hmac

from core.config import settings
from services.legacy_owner_cutover_types import LegacyOwnerRuntimeIdentity
from services.staff_user_service import StaffUserService


class LegacyOwnerRuntimeCredential:
    @classmethod
    def load(cls) -> LegacyOwnerRuntimeIdentity:
        normalized_name = StaffUserService.normalize_username(settings.ADMIN_USERNAME)
        credential = str(settings.ADMIN_PASSWORD or "")
        binding = hmac.new(
            cls._binding_key(),
            (str(normalized_name or "") + "\0" + credential).encode(
                "utf-8", errors="surrogatepass"
            ),
            hashlib.sha256,
        ).hexdigest()
        return LegacyOwnerRuntimeIdentity(
            normalized_name=normalized_name,
            credential=credential,
            identity_canonical=str(settings.ADMIN_USERNAME or "") == normalized_name,
            binding=binding,
        )

    @staticmethod
    def _binding_key() -> bytes:
        return hashlib.sha256(
            b"mvn:legacy-owner-cutover:runtime-binding:v1\0"
            + settings.SECRET_KEY.encode("utf-8")
        ).digest()


__all__ = ["LegacyOwnerRuntimeCredential"]
