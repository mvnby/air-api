"""System-owner-only ZAPRO.SU credential lifecycle."""

from __future__ import annotations

import hmac

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.integration_credential_keyring import (
    IntegrationCredentialUnavailable, IntegrationCredentialUnreadable,
)
from models import PlatformAIConnection
from services.zaprosu_provider_service import Completion, ZaprosuError, chat_completion, list_models

_CIPHER_CONTEXT = b"mvn.platform-ai.zaprosu.credentials.v1"
_FINGERPRINT_CONTEXT = b"mvn.platform-ai.zaprosu.fingerprint.v1"


class PlatformAICredentialCipher:
    @staticmethod
    def encrypt(key: str) -> str:
        ring = settings.integration_credential_keyring
        raw = key.encode("utf-8")
        try:
            if ring.enabled and ring.write_mode == "active":
                return ring.encrypt(raw, context=_CIPHER_CONTEXT)
            return ring.encrypt_legacy(raw, context=_CIPHER_CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""))
        except IntegrationCredentialUnavailable:
            raise ZaprosuError("credential_store_unavailable") from None

    @staticmethod
    def decrypt_with_source(value: str):
        try:
            result = settings.integration_credential_keyring.decrypt(
                value, context=_CIPHER_CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""),
            )
            return result.plaintext.decode("utf-8"), result
        except (IntegrationCredentialUnavailable, IntegrationCredentialUnreadable, UnicodeError):
            raise ZaprosuError("credential_unreadable") from None

    @staticmethod
    def fingerprint(key: str) -> str:
        ring = settings.integration_credential_keyring
        raw = key.encode("utf-8")
        try:
            if ring.enabled and ring.write_mode == "active":
                return ring.fingerprint(raw, context=_FINGERPRINT_CONTEXT)
            return ring.fingerprint_legacy(raw, context=_FINGERPRINT_CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""))
        except IntegrationCredentialUnavailable:
            raise ZaprosuError("credential_store_unavailable") from None


class PlatformAIConnectionService:
    @staticmethod
    async def get(session: AsyncSession) -> PlatformAIConnection | None:
        return await session.get(PlatformAIConnection, 1)

    @staticmethod
    def public(row: PlatformAIConnection | None) -> dict:
        return {
            "configured": row is not None,
            "enabled": bool(row.enabled) if row else False,
            "selected_model": row.selected_model if row else None,
        }

    @classmethod
    async def save(cls, session: AsyncSession, *, key: str | None, enabled: bool | None, model: str | None) -> dict:
        row = await cls.get(session)
        new_key = (key or "").strip()
        if new_key:
            if len(new_key) > 4096 or any(ch.isspace() for ch in new_key):
                raise ZaprosuError("invalid_credential")
            cipher = PlatformAICredentialCipher.encrypt(new_key)
            fingerprint = PlatformAICredentialCipher.fingerprint(new_key)
            if row is None:
                row = PlatformAIConnection(id=1, encrypted_credentials=cipher, credentials_fingerprint=fingerprint)
            else:
                row.encrypted_credentials = cipher
                row.credentials_fingerprint = fingerprint
        if row is None:
            raise ZaprosuError("not_configured")
        if model is not None:
            if model and (len(model) > 160 or any(ch.isspace() for ch in model)):
                raise ZaprosuError("invalid_model")
            row.selected_model = model or None
        if enabled is not None:
            row.enabled = enabled
        if row.enabled and not row.selected_model:
            raise ZaprosuError("model_required")
        session.add(row)
        await session.commit()
        return cls.public(row)

    @classmethod
    async def delete(cls, session: AsyncSession) -> None:
        row = await cls.get(session)
        if row:
            await session.delete(row)
            await session.commit()

    @staticmethod
    def key(row: PlatformAIConnection | None, *, require_enabled: bool = False) -> str:
        if row is None or (require_enabled and not row.enabled):
            raise ZaprosuError("not_configured")
        return PlatformAICredentialCipher.decrypt_with_source(row.encrypted_credentials)[0]

    @classmethod
    async def models(cls, session: AsyncSession) -> list[str]:
        return await list_models(cls.key(await cls.get(session)))

    @classmethod
    async def test(cls, session: AsyncSession) -> Completion:
        row = await cls.get(session)
        if row is None or not row.selected_model:
            raise ZaprosuError("model_required")
        return await chat_completion(
            token=cls.key(row), model=row.selected_model,
            prompt="Ответь только словом OK.", max_output_tokens=16,
        )

    @classmethod
    async def complete(cls, session: AsyncSession, *, prompt: str, system_prompt: str = "", max_output_tokens: int = 256) -> Completion:
        """Explicit opt-in for trusted platform call sites only; never a partner fallback."""
        row = await cls.get(session)
        if row is None or not row.enabled or not row.selected_model:
            raise ZaprosuError("not_configured")
        return await chat_completion(
            token=cls.key(row, require_enabled=True), model=row.selected_model,
            prompt=prompt, system_prompt=system_prompt, max_output_tokens=max_output_tokens,
        )

    @staticmethod
    def fingerprint_matches(row: PlatformAIConnection, key: str, source: str) -> bool:
        return source != "active" or hmac.compare_digest(row.credentials_fingerprint, PlatformAICredentialCipher.fingerprint(key))
