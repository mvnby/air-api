import json

import httpx
import pytest

from services.deepseek_provider_service import (
    DefectActAIProviderError,
    request_deepseek_completion,
)


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


class _RecordingClient:
    response: httpx.Response
    init_kwargs: dict = {}
    request: httpx.Request | None = None

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, **_kwargs):
        type(self).request = request
        return self.response


def _response(*chunks: bytes, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        headers=headers or {"Content-Type": "application/json"},
        stream=_ChunkStream(*chunks),
        request=httpx.Request("POST", "https://api.invalid/chat"),
    )


@pytest.mark.asyncio
async def test_deepseek_transport_is_bounded_and_disables_environment_proxy(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}]}).encode()
    _RecordingClient.response = _response(body)
    monkeypatch.setattr("services.deepseek_provider_service.settings.DEEPSEEK_TOKEN", "token")
    monkeypatch.setattr("services.deepseek_provider_service.httpx.AsyncClient", _RecordingClient)

    result = await request_deepseek_completion(
        prompt="prompt",
        system_prompt="system",
        temperature=0.1,
        thinking_enabled=False,
    )

    assert result == '{"ok":true}'
    assert _RecordingClient.init_kwargs["trust_env"] is False
    request_payload = json.loads(_RecordingClient.request.content)
    assert request_payload["max_tokens"] == 4096
    assert request_payload["thinking"] == {"type": "disabled"}
    assert _RecordingClient.request.headers["accept-encoding"] == "identity"


@pytest.mark.asyncio
async def test_deepseek_transport_rejects_oversized_chunked_response(monkeypatch):
    _RecordingClient.response = _response(b"1234", b"5678")
    monkeypatch.setattr("services.deepseek_provider_service.settings.DEEPSEEK_TOKEN", "token")
    monkeypatch.setattr("services.deepseek_provider_service.MAX_DEEPSEEK_RESPONSE_BYTES", 7)
    monkeypatch.setattr("services.deepseek_provider_service.httpx.AsyncClient", _RecordingClient)

    with pytest.raises(DefectActAIProviderError) as error:
        await request_deepseek_completion(
            prompt="prompt",
            system_prompt="system",
            temperature=0.1,
        )
    assert error.value.code == "invalid_response"


@pytest.mark.asyncio
async def test_deepseek_transport_rejects_compressed_response(monkeypatch):
    _RecordingClient.response = _response(
        b"compressed",
        headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
    )
    monkeypatch.setattr("services.deepseek_provider_service.settings.DEEPSEEK_TOKEN", "token")
    monkeypatch.setattr("services.deepseek_provider_service.httpx.AsyncClient", _RecordingClient)

    with pytest.raises(DefectActAIProviderError) as error:
        await request_deepseek_completion(
            prompt="prompt",
            system_prompt="system",
            temperature=0.1,
        )
    assert error.value.code == "invalid_response"
