import json

import httpx
import pytest

from services import tender_openai_provider as provider


MODEL = "gpt-5.4-mini-2026-03-17"
CANDIDATES = '{"facts":[{"kind":"work","fragment":0,"quote":"Техническое обслуживание"}]}'


def completed(content):
    return {
        "status": "completed",
        "model": MODEL,
        "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [content]}],
    }


@pytest.fixture
def install_transport(monkeypatch):
    original_client = httpx.AsyncClient
    monkeypatch.setattr(provider.settings, "OPENAI_API_KEY", "sample-key")
    monkeypatch.setattr(provider.settings, "TENDER_OPENAI_MODEL", "gpt-5.4-mini")

    def install(handler):
        def client(**kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(provider.httpx, "AsyncClient", client)

    return install


async def request_facts():
    return await provider.request_openai_tender_completion(
        prompt='[{"fragment":0,"text":"Техническое обслуживание"}]',
        system_prompt="Extract only verifiable facts.",
        fact_kinds=("work", "equipment"),
    )


@pytest.mark.asyncio
async def test_responses_request_and_actual_model(install_transport):
    def respond(request):
        assert request.url == "https://api.openai.com/v1/responses"
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer sample-key"
        assert request.headers["accept-encoding"] == "identity"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-5.4-mini"
        assert payload["store"] is False
        assert payload["tools"] == []
        assert payload["max_output_tokens"] == 8192
        assert payload["instructions"] == "Extract only verifiable facts."
        assert json.loads(payload["input"])[0]["text"] == "Техническое обслуживание"
        output = payload["text"]["format"]
        assert output["type"] == "json_schema"
        assert output["strict"] is True
        facts = output["schema"]["properties"]["facts"]
        assert facts["maxItems"] == 80
        assert facts["items"]["required"] == ["kind", "fragment", "quote"]
        assert facts["items"]["properties"]["kind"]["enum"] == ["work", "equipment"]
        return httpx.Response(200, json=completed({"type": "output_text", "text": CANDIDATES}))

    install_transport(respond)
    assert await request_facts() == (CANDIDATES, MODEL)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (307, {"error": "sample-key"}, "upstream_error"),
        (401, {"error": "sample-key"}, "authentication_rejected"),
        (429, {"error": "sample-key"}, "rate_limited"),
        (200, {"status": "incomplete"}, "incomplete"),
        (200, completed({"type": "refusal", "refusal": "sample-key"}), "refused"),
        (200, completed({"type": "output_text", "text": None}), "invalid_response"),
    ],
)
async def test_upstream_failures_are_bounded_and_sanitized(install_transport, status, body, code):
    attempts = []

    def respond(request):
        attempts.append(request)
        return httpx.Response(status, json=body, headers={"Location": "https://redirect.invalid/"})

    install_transport(respond)
    with pytest.raises(provider.OpenAITenderProviderError) as error:
        await request_facts()
    assert error.value.code == code
    assert "sample-key" not in str(error.value)
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_oversized_body_is_rejected(install_transport, monkeypatch):
    monkeypatch.setattr(provider, "_MAX_RESPONSE_BYTES", 64)
    install_transport(lambda _: httpx.Response(200, content=b"x" * 65))
    with pytest.raises(provider.OpenAITenderProviderError, match="response_too_large"):
        await request_facts()


@pytest.mark.asyncio
async def test_unsupported_model_is_rejected_before_network(install_transport, monkeypatch):
    monkeypatch.setattr(provider.settings, "TENDER_OPENAI_MODEL", "unknown-model")
    install_transport(lambda _: pytest.fail("No upstream request expected"))
    with pytest.raises(provider.OpenAITenderProviderError, match="unsupported_model"):
        await request_facts()
