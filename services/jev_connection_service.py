"""Write-only system credentials; enablement is explicit and has no env fallback."""
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.integration_credential_keyring import IntegrationCredentialUnavailable, IntegrationCredentialUnreadable
from models.jev_shadow import JevConnection

JEV_MODEL = "jev-1.13.0"
MAX_DAILY_REQUESTS = 500


class JevCredentialError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class JevCredentialCipher:
    _CONTEXT = b"mvn.platform-ai.jev.credentials.v1"
    _FINGERPRINT_CONTEXT = b"mvn.platform-ai.jev.fingerprint.v1"

    @classmethod
    def encrypt(cls, key: str) -> str:
        ring = settings.integration_credential_keyring
        try:
            if ring.enabled and ring.write_mode == "active":
                return ring.encrypt(key.encode(), context=cls._CONTEXT)
            return ring.encrypt_legacy(key.encode(), context=cls._CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""))
        except IntegrationCredentialUnavailable:
            raise JevCredentialError("credential_store_unavailable") from None

    @classmethod
    def decrypt_with_source(cls, value: str):
        try:
            result = settings.integration_credential_keyring.decrypt(value, context=cls._CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""))
            return result.plaintext.decode(), result
        except (IntegrationCredentialUnavailable, IntegrationCredentialUnreadable, UnicodeError):
            raise JevCredentialError("credential_unreadable") from None

    @classmethod
    def fingerprint(cls, key: str) -> str:
        ring = settings.integration_credential_keyring
        try:
            if ring.enabled and ring.write_mode == "active":
                return ring.fingerprint(key.encode(), context=cls._FINGERPRINT_CONTEXT)
            return ring.fingerprint_legacy(key.encode(), context=cls._FINGERPRINT_CONTEXT, local_legacy_secret=str(settings.SECRET_KEY or ""))
        except IntegrationCredentialUnavailable:
            raise JevCredentialError("credential_store_unavailable") from None


class JevConnectionService:
    @staticmethod
    async def get(session: AsyncSession, *, for_update=False):
        # A probe releases the transaction during inference. Refresh its cached
        # row when locking again so concurrent spend and a UTC rollover survive.
        return await session.get(JevConnection, 1, with_for_update=for_update, populate_existing=for_update)

    @staticmethod
    def public(row):
        today = bool(row and row.budget_day == datetime.now(timezone.utc).date())
        return {"configured": bool(row and row.encrypted_credentials), "enabled": bool(row and row.enabled),
                "model": JEV_MODEL, "daily_budget_usd": float(row.daily_budget_usd if row else Decimal("0.05")),
                "max_daily_requests": MAX_DAILY_REQUESTS,
                "today_requests": row.daily_requests if today else 0,
                "today_budget_used_usd": float(row.budget_used_usd) if today else 0}

    @classmethod
    async def save(cls, session, *, key=None, enabled=None, daily_budget_usd=None):
        row = await cls.get(session, for_update=True) or JevConnection()
        new_key = (key or "").strip()
        if new_key:
            if len(new_key) > 4096 or any(ch.isspace() for ch in new_key):
                raise JevCredentialError("invalid_credential")
            row.encrypted_credentials = JevCredentialCipher.encrypt(new_key)
            row.credentials_fingerprint = JevCredentialCipher.fingerprint(new_key)
        if enabled is not None:
            row.enabled = enabled
        if daily_budget_usd is not None:
            budget = Decimal(str(daily_budget_usd))
            if not budget.is_finite() or not Decimal("0") < budget <= Decimal("5"):
                raise JevCredentialError("invalid_budget")
            row.daily_budget_usd = budget
        if row.enabled and not row.encrypted_credentials:
            raise JevCredentialError("not_configured")
        session.add(row)
        await session.commit()
        return cls.public(row)

    @classmethod
    async def delete(cls, session):
        row = await cls.get(session, for_update=True) or JevConnection()
        row.enabled = False
        row.encrypted_credentials = row.credentials_fingerprint = None
        session.add(row)
        await session.commit()
        return cls.public(row)

    @classmethod
    async def test(cls, session):
        from services.jev_provider_service import classify_jev
        from crud import jev_shadow as dao
        row = await cls.get(session, for_update=True)
        if not row or not row.encrypted_credentials:
            raise JevCredentialError("not_configured")
        token = JevCredentialCipher.decrypt_with_source(row.encrypted_credentials)[0]
        dao.reset_budget_day(row, datetime.now(timezone.utc))
        if not dao.budget_available(row, max_daily_requests=MAX_DAILY_REQUESTS):
            raise JevCredentialError("budget_exhausted")
        dao.reserve_request(row)
        budget_day = row.budget_day
        session.add(row)
        await session.commit()
        result = await classify_jev(token=token, state="Customer asks to buy and install two air conditioners.")
        row = await cls.get(session, for_update=True)
        if row and row.budget_day == budget_day:
            row.budget_used_usd += result.estimated_usd - dao.RESERVATION_USD
            session.add(row)
            await session.commit()
        return {"ok": True, "model": result.model}
