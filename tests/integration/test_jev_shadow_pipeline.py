import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import JevShadowSample, Order
from models.tenancy import TenantScope
from services.email_lead_intake_service import EmailLeadIntakeService
from services.jev_connection_service import JevConnectionService
from services.jev_provider_service import JevResult
from services.jev_shadow_service import JevShadowService

SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.mark.asyncio
async def test_parallel_workers_charge_and_classify_one_replayed_email_once(db, monkeypatch):
    factory = sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("services.jev_shadow_service.async_session_maker", factory)
    await JevConnectionService.save(db, key="test-jev-key", enabled=True)
    primary = AsyncMock(return_value={"is_potential_order": False, "reason": "primary_rejected"})
    monkeypatch.setattr(EmailLeadIntakeService, "classify_email", primary)
    kwargs = dict(tenant_scope=SCOPE, sender_email="user@example.test", sender_name=None,
        subject="Монтаж кондиционера", raw_body="Нужен монтаж кондиционера", message_id="<shadow-test@example.test>")
    for _ in range(2):
        outcome = await EmailLeadIntakeService.process_email(db, **kwargs)
        assert outcome.status == "rejected"
    await db.rollback()
    provider = AsyncMock(return_value=JevResult(model="jev-1.13.0", kind="customer_request", kind_confidence=.95,
        hvac_probability=.9, input_tokens=1000, output_tokens=20, duration_ms=120))
    monkeypatch.setattr("services.jev_shadow_service.classify_jev", provider)
    completed = await asyncio.gather(*(JevShadowService.process_one() for _ in range(4)))
    assert sum(completed) == 1
    provider.assert_awaited_once()
    await db.rollback()
    assert (await db.execute(select(Order))).scalars().all() == []
    rows = (await db.execute(select(JevShadowSample))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "completed" and rows[0].jev_is_relevant
    assert rows[0].primary_is_relevant is False
    connection = await JevConnectionService.get(db)
    assert connection.daily_requests == 1 and connection.budget_used_usd == Decimal("0.00004200")


@pytest.mark.asyncio
async def test_primary_import_succeeds_when_shadow_database_is_unavailable_and_dry_run_skips_it(db, monkeypatch):
    primary = AsyncMock(return_value={"is_potential_order": False})
    monkeypatch.setattr(EmailLeadIntakeService, "classify_email", primary)
    def unavailable():
        raise RuntimeError("secret database details")
    monkeypatch.setattr("services.jev_shadow_service.async_session_maker", unavailable)
    kwargs = dict(tenant_scope=SCOPE, sender_email="user@example.test", sender_name=None,
        subject="Кондиционер", raw_body="Нужен кондиционер", message_id="<shadow-failure@example.test>")
    outcome = await EmailLeadIntakeService.process_email(db, **kwargs)
    assert outcome.status == "rejected"
    observer = AsyncMock()
    monkeypatch.setattr(JevShadowService, "enqueue", observer)
    await EmailLeadIntakeService.process_email(db, **kwargs, dry_run=True)
    observer.assert_not_called()
