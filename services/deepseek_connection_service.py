"""Platform-only DeepSeek key management and request-time credential resolution."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import async_session_maker
from core.integration_credential_keyring import (
    IntegrationCredentialUnavailable, IntegrationCredentialUnreadable,
)
from models.deepseek_connection import DeepSeekConnection


class DeepSeekCredentialError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class DeepSeekCredentialCipher:
    _CONTEXT = b"mvn.platform-ai.deepseek.credentials.v1"
    _FINGERPRINT_CONTEXT = b"mvn.platform-ai.deepseek.fingerprint.v1"

    @classmethod
    def encrypt(cls, key: str) -> str:
        ring = settings.integration_credential_keyring
        try:
            if ring.enabled and ring.write_mode == "active":
                return ring.encrypt(key.encode(), context=cls._CONTEXT)
            return ring.encrypt_legacy(key.encode(), context=cls._CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""))
        except IntegrationCredentialUnavailable:
            raise DeepSeekCredentialError("credential_store_unavailable") from None

    @classmethod
    def decrypt_with_source(cls, value: str):
        try:
            result = settings.integration_credential_keyring.decrypt(
                value, context=cls._CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""),
            )
            return result.plaintext.decode(), result
        except (IntegrationCredentialUnavailable, IntegrationCredentialUnreadable, UnicodeError):
            raise DeepSeekCredentialError("credential_unreadable") from None

    @classmethod
    def fingerprint(cls, key: str) -> str:
        ring = settings.integration_credential_keyring
        try:
            if ring.enabled and ring.write_mode == "active":
                return ring.fingerprint(key.encode(), context=cls._FINGERPRINT_CONTEXT)
            return ring.fingerprint_legacy(key.encode(), context=cls._FINGERPRINT_CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""))
        except IntegrationCredentialUnavailable:
            raise DeepSeekCredentialError("credential_store_unavailable") from None


class DeepSeekConnectionService:
    @staticmethod
    async def get(session: AsyncSession, *, for_update: bool = False) -> DeepSeekConnection | None:
        return await session.get(DeepSeekConnection, 1, with_for_update=for_update)

    @staticmethod
    def public(row: DeepSeekConnection | None) -> dict:
        environment_available = bool(settings.DEEPSEEK_TOKEN.strip())
        return {
            "configured": bool(row.encrypted_credentials) if row else environment_available,
            "enabled": row.enabled if row else environment_available,
            "source": "settings" if row else "environment" if environment_available else "none",
            "environment_key_available": environment_available,
        }

    @classmethod
    async def save(cls, session: AsyncSession, *, key: str | None, enabled: bool | None) -> dict:
        row = await cls.get(session, for_update=True)
        new_key = (key or "").strip()
        if row is None:
            # Materialize the effective environment key when disabling it or
            # saving an empty field. There is no fallback after the first save.
            new_key = new_key or settings.DEEPSEEK_TOKEN.strip()
            row = DeepSeekConnection(enabled=bool(settings.DEEPSEEK_TOKEN.strip()))
        if new_key:
            if len(new_key) > 4096 or any(ch.isspace() for ch in new_key):
                raise DeepSeekCredentialError("invalid_credential")
            row.encrypted_credentials = DeepSeekCredentialCipher.encrypt(new_key)
            row.credentials_fingerprint = DeepSeekCredentialCipher.fingerprint(new_key)
        if enabled is not None:
            row.enabled = enabled
        if row.enabled and not row.encrypted_credentials:
            raise DeepSeekCredentialError("not_configured")
        session.add(row)
        await session.commit()
        return cls.public(row)

    @classmethod
    async def import_environment(cls, session: AsyncSession) -> dict:
        row = await cls.get(session, for_update=True)
        if row is not None and row.encrypted_credentials:
            raise DeepSeekCredentialError("already_configured")
        if not settings.DEEPSEEK_TOKEN.strip():
            raise DeepSeekCredentialError("environment_key_unavailable")
        return await cls.save(session, key=settings.DEEPSEEK_TOKEN.strip(), enabled=True)

    @classmethod
    async def delete(cls, session: AsyncSession) -> dict:
        row = await cls.get(session, for_update=True) or DeepSeekConnection()
        row.encrypted_credentials = None
        row.credentials_fingerprint = None
        row.enabled = False
        session.add(row)
        await session.commit()
        return cls.public(row)

    @classmethod
    async def resolve_token(cls, session: AsyncSession, *, require_enabled: bool = True) -> str:
        row = await cls.get(session)
        if row is None:
            return settings.DEEPSEEK_TOKEN.strip()
        if not row.encrypted_credentials or (require_enabled and not row.enabled):
            return ""
        return DeepSeekCredentialCipher.decrypt_with_source(row.encrypted_credentials)[0]

    @classmethod
    async def test(cls, session: AsyncSession) -> dict:
        # Local import keeps the credential resolver independent of transport.
        from services.deepseek_provider_service import request_deepseek_completion

        token = await cls.resolve_token(session, require_enabled=False)
        if not token:
            raise DeepSeekCredentialError("not_configured")
        result = await request_deepseek_completion(
            prompt='Верни JSON: {"ok": true}', system_prompt="Ответь только JSON.",
            temperature=0, thinking_enabled=False, max_tokens=16,
            deadline_seconds=20, token=token,
        )
        try:
            return {"ok": json.loads(result).get("ok") is True}
        except (ValueError, AttributeError):
            raise DeepSeekCredentialError("invalid_response") from None


async def resolve_deepseek_token() -> str:
    # A fresh short-lived session on every request makes rotation work across
    # both HA nodes without process caches or holding a DB connection for AI.
    async with async_session_maker() as session:
        return await DeepSeekConnectionService.resolve_token(session)
