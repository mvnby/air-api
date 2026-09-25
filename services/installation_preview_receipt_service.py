"""Short-lived, scope-bound replay for immutable installation previews."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import InstallationPreviewSnapshot
from models.tenancy import TenantScope
from schemas_installation_price_book import InstallationPreviewPayload, InstallationPreviewResponse
from services.command_transaction import command_transaction
from services.public_write_idempotency_service import PublicWriteIdempotencyService


class InstallationPreviewReceiptService:
    TTL = timedelta(minutes=30)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def input_hash(payload: InstallationPreviewPayload) -> str:
        canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def key_hash(key: str) -> str:
        return PublicWriteIdempotencyService.key_hash(PublicWriteIdempotencyService.normalize_key(key))

    @staticmethod
    def _token(row: InstallationPreviewSnapshot) -> str:
        source = f"installation-preview-v1:{row.tenant_id}:{row.storefront_id}:{row.key_hash}:{row.input_hash}:{InstallationPreviewReceiptService._utc(row.created_at).isoformat()}"
        return hmac.new(settings.SECRET_KEY.encode(), source.encode(), hashlib.sha256).hexdigest()

    @classmethod
    def _response(cls, row: InstallationPreviewSnapshot, *, request_hash: str) -> InstallationPreviewResponse:
        if row.input_hash != request_hash:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_reused"})
        token = cls._token(row)
        if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), row.token_hash):
            raise HTTPException(status_code=503, detail={"code": "preview_ref_unavailable"}, headers={"Retry-After": "1"})
        response = InstallationPreviewResponse.model_validate(row.snapshot["result"])
        response.preview_ref = token
        response.expires_at = cls._utc(row.expires_at)
        return response

    @staticmethod
    async def _row(session: AsyncSession, scope: TenantScope, key_hash: str) -> InstallationPreviewSnapshot | None:
        return (await session.execute(select(InstallationPreviewSnapshot).where(
            InstallationPreviewSnapshot.tenant_id == scope.tenant_id,
            InstallationPreviewSnapshot.storefront_id == scope.storefront_id,
            InstallationPreviewSnapshot.key_hash == key_hash,
        ).limit(1))).scalars().first()

    @classmethod
    async def replay(
        cls, session: AsyncSession, scope: TenantScope, *, key_hash: str, request_hash: str,
    ) -> InstallationPreviewResponse | None:
        row = await cls._row(session, scope, key_hash)
        if row is None or cls._utc(row.expires_at) <= datetime.now(timezone.utc):
            return None
        return cls._response(row, request_hash=request_hash)

    @classmethod
    async def store_or_replay(
        cls, session: AsyncSession, scope: TenantScope, *, key_hash: str, request_hash: str,
        price_book_id: int, snapshot: dict,
    ) -> InstallationPreviewResponse:
        now = datetime.now(timezone.utc)
        expires = now + cls.TTL
        row = InstallationPreviewSnapshot(
            tenant_id=scope.tenant_id, storefront_id=scope.storefront_id, key_hash=key_hash,
            price_book_id=price_book_id, input_hash=request_hash, snapshot=snapshot,
            created_at=now, expires_at=expires, token_hash="",
        )
        row.token_hash = hashlib.sha256(cls._token(row).encode()).hexdigest()
        try:
            async with command_transaction(session):
                if session.get_bind().dialect.name == "postgresql":
                    await session.execute(text("SET LOCAL lock_timeout = '3000ms'"))
                await session.execute(delete(InstallationPreviewSnapshot).where(
                    InstallationPreviewSnapshot.tenant_id == scope.tenant_id,
                    InstallationPreviewSnapshot.storefront_id == scope.storefront_id,
                    InstallationPreviewSnapshot.key_hash == key_hash,
                    InstallationPreviewSnapshot.expires_at <= now,
                ))
                values = {column.name: getattr(row, column.name) for column in InstallationPreviewSnapshot.__table__.columns
                          if column.name != "id"}
                dialect = session.get_bind().dialect.name
                if dialect == "postgresql":
                    statement = postgresql_insert(InstallationPreviewSnapshot).values(**values)
                elif dialect == "sqlite":
                    statement = sqlite_insert(InstallationPreviewSnapshot).values(**values)
                else:  # pragma: no cover - production and tests use PostgreSQL/SQLite
                    raise RuntimeError(f"Unsupported preview receipt dialect: {dialect}")
                claimed_id = (await session.execute(statement.on_conflict_do_nothing(
                    index_elements=["tenant_id", "storefront_id", "key_hash"],
                ).returning(InstallationPreviewSnapshot.id))).scalar_one_or_none()
                if claimed_id is None:
                    existing = await cls._row(session, scope, key_hash)
                    if existing is None or cls._utc(existing.expires_at) <= now:
                        raise HTTPException(status_code=503, detail={"code": "preview_receipt_busy"}, headers={"Retry-After": "1"})
                    return cls._response(existing, request_hash=request_hash)
                return cls._response(row, request_hash=request_hash)
        except DBAPIError as exc:
            original = getattr(exc, "orig", None)
            if getattr(original, "sqlstate", None) == "55P03":
                raise HTTPException(status_code=503, detail={"code": "preview_receipt_busy"}, headers={"Retry-After": "1"}) from exc
            raise
