from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, func, select

from models import InstallationPriceBook, InstallationPreviewSnapshot, Storefront, Tenant
from models.tenancy import TenantScope
from schemas_installation_price_book import InstallationPreviewPayload, InstallationPreviewResponse
from services.installation_preview_receipt_service import InstallationPreviewReceiptService as Receipts
from services.installation_preview_retention_service import InstallationPreviewRetentionService


@pytest.mark.asyncio
async def test_preview_receipt_replays_rejects_changed_input_and_expires(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'preview.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=501, storefront_id=502)
    try:
        async with factory() as session:
            session.add(Tenant(id=501, slug="preview-receipt", display_name="Preview receipt"))
            session.add(Storefront(id=502, tenant_id=501, slug="main", display_name="Main",
                                   status="active", is_default=True))
            session.add(Storefront(id=503, tenant_id=501, slug="other", display_name="Other",
                                   status="active", is_default=False))
            book = InstallationPriceBook(tenant_id=501, revision=1, fingerprint="test", entries=[])
            session.add(book)
            await session.commit()
            payload = InstallationPreviewPayload.model_validate({"installations": [
                {"key": "one", "typed_profile": {"product_kind": "complete_split_system",
                 "indoor_type": "wall", "confirmed": True}, "route_length_m": 3, "holes_by_type": {}}
            ]})
            request_hash = Receipts.input_hash(payload)
            key_hash = Receipts.key_hash("receipt-request-key-one")
            result = InstallationPreviewResponse(status="fixed", scope_ref="scope", total="500.00")
            snapshot = {"result": result.model_dump(mode="json")}
            first = await Receipts.store_or_replay(session, scope, key_hash=key_hash,
                request_hash=request_hash, price_book_id=book.id, snapshot=snapshot)
            assert first.preview_ref and first.expires_at
            assert await Receipts.replay(session, scope, key_hash=key_hash, request_hash=request_hash) == first
            second = await Receipts.store_or_replay(session, scope, key_hash=key_hash,
                request_hash=request_hash, price_book_id=book.id, snapshot=snapshot)
            assert second == first
            other_scope = TenantScope(tenant_id=501, storefront_id=503)
            other = await Receipts.store_or_replay(session, other_scope, key_hash=key_hash,
                request_hash=request_hash, price_book_id=book.id, snapshot=snapshot)
            assert other.preview_ref != first.preview_ref
            in_scope = select(InstallationPreviewSnapshot).where(
                InstallationPreviewSnapshot.storefront_id == scope.storefront_id)
            assert await session.scalar(select(func.count(InstallationPreviewSnapshot.id)).where(
                InstallationPreviewSnapshot.storefront_id == scope.storefront_id)) == 1
            saved = (await session.execute(in_scope)).scalar_one()
            assert saved.token_hash != first.preview_ref
            assert saved.key_hash != "receipt-request-key-one"
            with pytest.raises(HTTPException) as error:
                await Receipts.replay(session, scope, key_hash=key_hash, request_hash="different-input")
            assert error.value.status_code == 409
            saved.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(saved)
            await session.commit()
            assert await Receipts.replay(session, scope, key_hash=key_hash, request_hash=request_hash) is None
            replacement = await Receipts.store_or_replay(session, scope, key_hash=key_hash,
                request_hash=request_hash, price_book_id=book.id, snapshot=snapshot)
            assert replacement.preview_ref != first.preview_ref
            assert await session.scalar(select(func.count(InstallationPreviewSnapshot.id)).where(
                InstallationPreviewSnapshot.storefront_id == scope.storefront_id)) == 1
            saved = (await session.execute(in_scope)).scalar_one()
            saved.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(saved)
            await session.commit()
            assert await InstallationPreviewRetentionService.delete_expired_batch(session, limit=1) == 1
            await session.commit()
            assert await session.scalar(select(func.count(InstallationPreviewSnapshot.id))) == 1
    finally:
        await engine.dispose()
