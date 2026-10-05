from unittest.mock import AsyncMock, MagicMock

import pytest

from services.belzakupki_source_analysis import MAX_TENDER_TEXT_CHARS, analyze_tender_text


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
