"""PostgreSQL proof for the importer unique key under concurrent profiles."""

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import BelzakupkiImportCheckpoint, Order
from services.belzakupki_import_service import BelzakupkiImportService
from services.tenant_scope_service import TenantScope


SCOPE = TenantScope(
    tenant_id=1,
    storefront_id=1,
    is_system=True,
    is_canonical_storefront=True,
)
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _item(profile_id: int) -> dict:
    return {
        "id": profile_id,
        "updated_at": "2026-09-19T10:00:00+00:00",
        "profile": {"id": profile_id, "name": f"Profile {profile_id}"},
        "score": 0.95,
        "relevance_status": "confirmed",
        "eligible": True,
        "reason": "HVAC",
        "ai_analysis": None,
        "tender": {
            "id": 99,
            "source": "belzakupki",
            "external_id": "shared-tender",
            "title": "Shared tender",
            "customer_name": "Customer",
            "url": "https://belzakupki.example/shared-tender",
            "deadline_at": "2026-10-01T00:00:00+00:00",
            "published_at": "2026-09-18T00:00:00+00:00",
            "estimated_value": 100,
            "contacts": [],
            "ai_analysis": None,
        },
    }


@pytest.mark.asyncio
async def test_postgres_concurrent_matching_profiles_create_one_tender_order(db_engine):
    sessions = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        await BelzakupkiImportService.import_page(
            session,
            tenant_scope=SCOPE,
            page={"items": [], "next_cursor": "cursor-0", "has_more": True},
            cursor_before=None,
            now=NOW,
        )

    async def import_for_profile(profile_id: int):
        async with sessions() as session:
            return await BelzakupkiImportService.import_page(
                session,
                tenant_scope=SCOPE,
                page={"items": [_item(profile_id)], "next_cursor": "cursor-1", "has_more": True},
                cursor_before="cursor-0",
                now=NOW,
            )

    first, second = await asyncio.gather(import_for_profile(1), import_for_profile(2))

    async with sessions() as session:
        orders = list((await session.execute(select(Order))).scalars())
        checkpoint = (await session.execute(select(BelzakupkiImportCheckpoint))).scalar_one()

    assert len(orders) == 1
    assert first.created + second.created == 1
    assert checkpoint.cursor == "cursor-1"
    # The second worker may become stale after the first moves the shared
    # checkpoint. It must not create a duplicate; the next full scan will
    # reconcile its profile update.
    assert set(orders[0].technical_meta["belzakupki"]["matches"]).issubset({"1", "2"})
