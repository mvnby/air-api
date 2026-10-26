from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.mail_wording_service import MailWordingService as Wording


@pytest.mark.parametrize("text", [
    "Монтаж выполним завтра, бесплатно доставим оборудование.",
    "Предоставим гарантию на все работы и скидку.",
    "Стоимость составит 1620 BYN, товары есть в наличии.",
    "Направляем предложение на ремонт и монтаж оборудования.",
    "Направляем предложение на доставку и монтаж оборудования.",
])
def test_rejects_new_facts_and_unsupported_work(text):
    assert not Wording.valid_introduction(text, "Направляем коммерческое предложение на диагностику оборудования.")


def test_dismantling_does_not_authorize_installation_wording():
    assert not Wording.valid_introduction(
        "Во вложении предложение на монтаж оборудования.",
        "Направляем коммерческое предложение на демонтаж оборудования.")


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    '{"introduction":"Во вложении предложение с составом монтажных работ. Посмотрите, подходит ли вам этот вариант."}',
    '{"introduction":"Доставим всё завтра бесплатно со скидкой."}',
    "malformed",
    None,
])
async def test_ai_refines_only_introduction_preserving_signature_and_next_step(monkeypatch, response):
    body = "Добрый день!\n\nНаправляем коммерческое предложение на монтаж оборудования.\nДокумент приложен к письму.\n\nПосмотрите состав работ и сообщите замечания.\n\nС уважением,\nВадим\nМастер Воздуха\nsales@example.test"
    row = SimpleNamespace(id=80, version=3, status="draft", order_id=590, subject="КП на монтаж", body_text=body)
    monkeypatch.setattr("services.mail_wording_service.MailWorkspaceService._get", AsyncMock(return_value=row))
    monkeypatch.setattr("services.mail_wording_service.MailWorkspaceDAO.attachments", AsyncMock(return_value=[
        SimpleNamespace(source_metadata={"document_type": "offer", "mail_scenario": "монтаж оборудования", "mail_context": [{"kind": "service", "title": "Стандартный монтаж", "constraints": "Без доставки"}]})]))
    provider = AsyncMock(return_value=response)
    if response is None:
        provider.side_effect = TimeoutError()
    monkeypatch.setattr("services.deepseek_provider_service.request_deepseek_completion", provider)
    result = await Wording.suggest(None, actor=SimpleNamespace(tenant_scope=SimpleNamespace(tenant_id=1)), draft_id=80, expected_version=3)
    assert result.version == 3 and result.subject == row.subject
    assert result.body_text.endswith("Посмотрите состав работ и сообщите замечания.\n\nС уважением,\nВадим\nМастер Воздуха\nsales@example.test")
    assert row.body_text == body  # No automatic server mutation or approval.
    if response and response.startswith('{"introduction":"Во вложении'):
        assert "Во вложении предложение" in result.body_text
    else:
        assert result.body_text == body
    assert "sales@example.test" not in provider.call_args.kwargs["prompt"]
