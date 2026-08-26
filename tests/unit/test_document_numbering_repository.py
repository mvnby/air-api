from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models import (
    DocumentLegalEntity,
    DocumentNumberReservation,
    DocumentNumberSequence,
    Tenant,
)
from modules.documents.domain import DocumentNumberScope
from modules.documents.infrastructure import DocumentNumberingRepository


@pytest.mark.asyncio
async def test_number_reservation_is_sequential_durable_and_idempotent(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'documents.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Tenant.__table__.create)
        await connection.run_sync(DocumentLegalEntity.__table__.create)
        await connection.execute(
            text(
                "CREATE TABLE order_document ("
                "id INTEGER PRIMARY KEY, tenant_id INTEGER, legal_entity_id INTEGER, "
                "UNIQUE (id, tenant_id, legal_entity_id))"
            )
        )
        await connection.run_sync(DocumentNumberSequence.__table__.create)
        await connection.run_sync(DocumentNumberReservation.__table__.create)

    try:
        async with sessions.begin() as session:
            tenant = Tenant(slug="mvn", display_name="MVN")
            session.add(tenant)
            await session.flush()
            entity = DocumentLegalEntity(
                tenant_id=tenant.id,
                slug="main",
                display_name="Main legal entity",
            )
            session.add(entity)
            await session.flush()
            tenant_id = int(tenant.id)
            legal_entity_id = int(entity.id)

        scope = DocumentNumberScope(
            tenant_id=tenant_id,
            legal_entity_id=legal_entity_id,
            document_type="invoice",
            series="СФ-2026-",
            period_key="2026",
        )
        async with sessions.begin() as session:
            first = await DocumentNumberingRepository.reserve(
                session,
                scope=scope,
                idempotency_key="issue:order-279:invoice",
            )
        async with sessions.begin() as session:
            replay = await DocumentNumberingRepository.reserve(
                session,
                scope=scope,
                idempotency_key="issue:order-279:invoice",
            )
            second = await DocumentNumberingRepository.reserve(
                session,
                scope=scope,
                idempotency_key="issue:order-280:invoice",
            )

        assert first.number_text == "СФ-2026-001"
        assert replay.reservation_id == first.reservation_id
        assert replay.reused is True
        assert second.number_text == "СФ-2026-002"
        async with sessions() as session:
            count = (
                await session.execute(
                    text("SELECT count(*) FROM document_number_reservation")
                )
            ).scalar_one()
            last_value = (
                await session.execute(
                    text("SELECT last_value FROM document_number_sequence")
                )
            ).scalar_one()
        assert count == 2
        assert last_value == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_idempotency_key_cannot_cross_numbering_scopes(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scope.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Tenant.__table__.create)
        await connection.run_sync(DocumentLegalEntity.__table__.create)
        await connection.execute(
            text(
                "CREATE TABLE order_document ("
                "id INTEGER PRIMARY KEY, tenant_id INTEGER, legal_entity_id INTEGER, "
                "UNIQUE (id, tenant_id, legal_entity_id))"
            )
        )
        await connection.run_sync(DocumentNumberSequence.__table__.create)
        await connection.run_sync(DocumentNumberReservation.__table__.create)

    try:
        async with sessions.begin() as session:
            tenant = Tenant(slug="scope", display_name="Scope")
            session.add(tenant)
            await session.flush()
            entity = DocumentLegalEntity(
                tenant_id=tenant.id, slug="main", display_name="Main"
            )
            session.add(entity)
            await session.flush()
            invoice = DocumentNumberScope(
                int(tenant.id), int(entity.id), "invoice", "I-", "2026"
            )
            act = DocumentNumberScope(
                int(tenant.id), int(entity.id), "act", "A-", "2026"
            )

        async with sessions.begin() as session:
            await DocumentNumberingRepository.reserve(
                session,
                scope=invoice,
                idempotency_key="same-command",
            )
        async with sessions.begin() as session:
            with pytest.raises(ValueError, match="another numbering scope"):
                await DocumentNumberingRepository.reserve(
                    session,
                    scope=act,
                    idempotency_key="same-command",
                )
    finally:
        await engine.dispose()
