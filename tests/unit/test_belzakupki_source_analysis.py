import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import SourceObjectDraft
from services.belzakupki_source_analysis import (
    MAX_TENDER_TEXT_CHARS,
    TenderAnalysisBusy,
    TenderAnalysisReuse,
    analyze_tender_text,
)


@pytest.mark.asyncio
async def test_analysis_includes_later_document_past_old_shared_budget(monkeypatch):
    monkeypatch.setattr("services.belzakupki_source_analysis.resolve_deepseek_token", AsyncMock(return_value="test-token"))
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": '{"work_summary":"Работы","objects":[]}'}}]}
    client = AsyncMock()
    client.post.return_value = response
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=client)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("services.belzakupki_source_analysis.httpx.AsyncClient", MagicMock(return_value=manager))
    raw = "Документ 1: " + "а" * 25000 + "\nДокумент 8: поздние подтверждённые факты"
    await analyze_tender_text(raw)
    sent = client.post.await_args.kwargs["json"]["messages"][1]["content"]
    assert sent.endswith(raw)


@pytest.mark.asyncio
async def test_oversize_analysis_fails_before_paid_request(monkeypatch):
    token = AsyncMock()
    monkeypatch.setattr("services.belzakupki_source_analysis.resolve_deepseek_token", token)
    with pytest.raises(ValueError, match="текст не будет обрезан"):
        await analyze_tender_text("а" * (MAX_TENDER_TEXT_CHARS + 1))
    token.assert_not_awaited()


@pytest.mark.asyncio
async def test_automatic_review_shares_inflight_and_completed_drafts(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def analyze(_):
        started.set()
        await release.wait()
        return ("Перенос сплит-системы", None, [SourceObjectDraft(address="Лепель")])

    provider = AsyncMock(side_effect=analyze)
    monkeypatch.setattr("services.belzakupki_source_analysis.analyze_tender_text", provider)
    scope = TenantScope(tenant_id=1, storefront_id=1)
    cache = TenderAnalysisReuse()
    first = asyncio.create_task(cache.analyze("ТЗ №699", scope=scope, order_id=699))
    await started.wait()
    second = asyncio.create_task(cache.analyze("ТЗ №699", scope=scope, order_id=699))
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    result = await second
    result[2][0].address = "Исправление менеджера"
    reopened = await cache.analyze("ТЗ №699", scope=scope, order_id=699)
    assert reopened[2][0].address == "Лепель"
    provider.assert_awaited_once_with("ТЗ №699")


@pytest.mark.asyncio
async def test_automatic_review_recomputes_across_scope_text_and_expiry(monkeypatch):
    now = 10.0
    monkeypatch.setattr("services.belzakupki_source_analysis.monotonic", lambda: now)
    provider = AsyncMock(return_value=("Работы", None, []))
    monkeypatch.setattr("services.belzakupki_source_analysis.analyze_tender_text", provider)
    scope = TenantScope(tenant_id=1, storefront_id=1)
    other = TenantScope(tenant_id=2, storefront_id=2)
    cache = TenderAnalysisReuse()
    await cache.analyze("ТЗ", scope=scope, order_id=699)
    await cache.analyze("ТЗ", scope=other, order_id=699)
    await cache.analyze("ТЗ изменилось", scope=scope, order_id=699)
    now += cache.TTL_SECONDS + 1
    await cache.analyze("ТЗ", scope=scope, order_id=699)
    assert [call.args[0] for call in provider.await_args_list] == ["ТЗ", "ТЗ", "ТЗ изменилось", "ТЗ"]


@pytest.mark.asyncio
async def test_automatic_review_caps_distinct_jobs_and_does_not_cache_errors(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def analyze(text):
        calls.append(text)
        if len(calls) == 2:
            started.set()
        await release.wait()
        if text == "Дефектный акт" and calls.count(text) == 1:
            raise RuntimeError("Temporary failure")
        return ("Работы", None, [])

    monkeypatch.setattr("services.belzakupki_source_analysis.analyze_tender_text", analyze)
    scope = TenantScope(tenant_id=1, storefront_id=1)
    cache = TenderAnalysisReuse()
    first = asyncio.create_task(cache.analyze("Дефектный акт", scope=scope, order_id=699))
    second = asyncio.create_task(cache.analyze("Другое ТЗ", scope=scope, order_id=700))
    await started.wait()
    with pytest.raises(TenderAnalysisBusy):
        await cache.analyze("Третий набор", scope=scope, order_id=701)
    release.set()
    with pytest.raises(RuntimeError, match="Temporary failure"):
        await first
    await second
    assert await cache.analyze("Дефектный акт", scope=scope, order_id=699) == ("Работы", None, [])
    assert set(calls[:2]) == {"Дефектный акт", "Другое ТЗ"}
    assert calls[2:] == ["Дефектный акт"]
