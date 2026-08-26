from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from models import DocumentLegalEntity
from modules.documents.domain import DocumentNumberScope
from modules.documents.infrastructure import DocumentNumberingRepository


@pytest.mark.asyncio
async def test_postgres_document_number_reservation_is_atomic_and_idempotent(
    db_engine,
) -> None:
    assert db_engine.dialect.name == "postgresql"
    sessions = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions.begin() as session:
        entity = DocumentLegalEntity(
            tenant_id=1,
            slug="numbering-main",
            display_name="Numbering main",
            is_default=True,
        )
        session.add(entity)
        await session.flush()
        legal_entity_id = int(entity.id)

    scope = DocumentNumberScope(
        tenant_id=1,
        legal_entity_id=legal_entity_id,
        document_type="invoice",
        series="СФ-2026-",
        period_key="2026",
    )

    async def reserve(key: str):
        async with sessions.begin() as session:
            return await DocumentNumberingRepository.reserve(
                session,
                scope=scope,
                idempotency_key=key,
            )

    distinct = await asyncio.gather(
        *(reserve(f"invoice-command-{index}") for index in range(8))
    )
    assert sorted(item.number_value for item in distinct) == list(range(1, 9))
    assert len({item.reservation_id for item in distinct}) == 8

    replay_a, replay_b = await asyncio.gather(
        reserve("same-issue-command"),
        reserve("same-issue-command"),
    )
    assert replay_a.reservation_id == replay_b.reservation_id
    assert replay_a.number_value == replay_b.number_value == 9
    assert {replay_a.reused, replay_b.reused} == {False, True}
