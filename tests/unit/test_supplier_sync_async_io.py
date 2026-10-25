import asyncio
from decimal import Decimal
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services import supplier_sync_service as sync


@pytest.fixture
def source_runtime(monkeypatch):
    source = SimpleNamespace(
        id=7, supplier_id=3, source_type="google_sheet", sheet_name="Prices", range_a1="A2:F9",
        col_title="A", col_qty="B", col_wholesale="C", col_rrc_byn="D",
        col_external_id="E", col_source_url="F", col_wholesale_currency="USD",
    )
    run = SimpleNamespace(id=11, source_id=source.id)
    session = SimpleNamespace(commit=AsyncMock(), add=Mock())

    async def finish_run(_session, result, **values):
        result.__dict__.update(values)
        return result

    monkeypatch.setattr(sync.SupplierSyncRunDAO, "create_run", AsyncMock(return_value=run))
    monkeypatch.setattr(sync.SupplierSyncRunDAO, "finish_run", finish_run)
    monkeypatch.setattr(
        sync.SupplierDAO, "get_supplier", AsyncMock(return_value=SimpleNamespace(spreadsheet_id="sheet-1")),
    )
    monkeypatch.setattr(sync.SupplierSourceDAO, "list_active_sync_sources", AsyncMock(return_value=[source]))
    upsert = AsyncMock()
    deactivate = AsyncMock(return_value=0)
    monkeypatch.setattr(sync.SupplierOfferDAO, "upsert_offer", upsert)
    monkeypatch.setattr(sync.SupplierOfferDAO, "deactivate_missing_offers", deactivate)
    return SimpleNamespace(source=source, session=session, upsert=upsert, deactivate=deactivate)


@pytest.mark.asyncio
async def test_slow_sheet_read_keeps_event_loop_responsive_and_database_on_its_owner_thread(
    monkeypatch, source_runtime,
):
    loop = asyncio.get_running_loop()
    owner_thread = get_ident()
    release_read = Event()
    responsive = Event()

    def heartbeat():
        responsive.set()
        release_read.set()

    def read_sheet_values(**kwargs):
        assert get_ident() != owner_thread
        assert kwargs == {"spreadsheet_id": "sheet-1", "sheet_name": "Prices", "range_a1": "A2:F9"}
        loop.call_soon_threadsafe(heartbeat)
        assert release_read.wait(timeout=1), "Google Sheets blocked the API event loop"
        return [["MDV MDSAG-09HRFN8", "2", "100", "350", "offer-1", ""]]

    def google_service():
        # Credential loading/refresh must also stay outside the event loop.
        assert get_ident() != owner_thread
        return SimpleNamespace(read_sheet_values=read_sheet_values)

    async def upsert(session, payload):
        assert get_ident() == owner_thread
        assert session is source_runtime.session
        assert payload["external_id"] == "offer-1"
        assert payload["wholesale_value"] == Decimal("100")
        assert payload["rrc_byn"] == Decimal("350")
        assert payload["qty"] == 2

    source_runtime.upsert.side_effect = upsert
    monkeypatch.setattr(sync, "get_google_service", google_service)

    result = await sync.SupplierSyncService.sync_source(source_runtime.session, source_runtime.source)

    assert responsive.is_set()
    assert result["status"] == "success"
    assert result["rows_total"] == result["rows_upserted"] == 1
    assert source_runtime.source.last_sync_status == "success"
    source_runtime.upsert.assert_awaited_once()
    source_runtime.deactivate.assert_awaited_once_with(
        session=source_runtime.session, supplier_id=3, present_external_ids={"offer-1"},
    )


@pytest.mark.asyncio
async def test_sheet_read_failure_remains_a_failed_sync_without_deactivating_offers(monkeypatch, source_runtime):
    def read_sheet_values(**_kwargs):
        raise OSError("Google Sheets unavailable")

    monkeypatch.setattr(
        sync, "get_google_service", lambda: SimpleNamespace(read_sheet_values=read_sheet_values),
    )

    result = await sync.SupplierSyncService.sync_source(source_runtime.session, source_runtime.source)

    assert result["status"] == "error"
    assert result["error"] == "Google Sheets unavailable"
    assert source_runtime.source.last_sync_status == "error"
    source_runtime.upsert.assert_not_awaited()
    source_runtime.deactivate.assert_not_awaited()
