"""Shared password policy and bcrypt operations for staff credentials."""

import asyncio

import bcrypt

from services.credential_policy import CredentialPolicy, CredentialPolicyError


class CredentialService(CredentialPolicy):
    # Cost-matched non-credential hash used to avoid revealing whether a staff
    # username has a usable password through response timing.
    DUMMY_PASSWORD_HASH = "$2b$12$vUbirU34FCJ9Ki/.2IXnLOKGyNOPfEcwT6hk9crUkMMZ2r.1Oat5a"

    @classmethod
    def hash_password(cls, password: str) -> str:
        value = cls.validate_password(password)
        return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @classmethod
    def verify_password(cls, password: str, password_hash: str | None) -> bool:
        if not password_hash:
            return False
        value = str(password or "")
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        if len(encoded) > cls.MAX_PASSWORD_UTF8_BYTES:
            return False
        try:
            return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
        except (TypeError, ValueError):
            return False

    @classmethod
    async def verify_password_async(
        cls,
        password: str,
        password_hash: str | None,
    ) -> bool:
        return await asyncio.to_thread(cls.verify_password, password, password_hash)


__all__ = ["CredentialPolicyError", "CredentialService"]
