import json

import httpx
import pytest

from services import zaprosu_provider_service as provider


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks): self.chunks = chunks
    async def __aiter__(self):
        for chunk in self.chunks: yield chunk


class _Client:
    response = None
    request = None
    kwargs = None
    def __init__(self, **kwargs): type(self).kwargs = kwargs
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass
    def build_request(self, method, url, **kwargs): return httpx.Request(method, url, **kwargs)
    async def send(self, request, **_):
        type(self).request = request
        return type(self).response


def _response(status, body, **headers):
    return httpx.Response(status, headers=headers, stream=_ChunkStream(body), request=httpx.Request("GET", "https://po.zapro.su/v1/models"))


@pytest.mark.asyncio
async def test_models_are_dynamic_ids_without_inferred_capabilities(monkeypatch):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    _Client.response = _response(200, json.dumps({"data": [{"id": "cheap-cn"}, {"id": "other"}, {"id": "cheap-cn"}]}).encode())
    assert await provider.list_models("secret-key") == ["cheap-cn", "other"]
    assert _Client.request.url == "https://po.zapro.su/v1/models"
    assert _Client.request.headers["authorization"] == "Bearer secret-key"
    assert _Client.kwargs["trust_env"] is False
    assert _Client.kwargs["follow_redirects"] is False


@pytest.mark.asyncio
async def test_completion_payload_limits_and_usage(monkeypatch):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    _Client.response = _response(200, json.dumps({"model": "cheap-cn", "choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}).encode())
    result = await provider.chat_completion(token="secret-key", model="cheap-cn", prompt="test", max_output_tokens=16)
    assert result.text == "OK" and result.prompt_tokens == 3
    payload = json.loads(_Client.request.content)
    assert payload == {"model": "cheap-cn", "messages": [{"role": "user", "content": "test"}], "max_tokens": 16, "stream": False}
    with pytest.raises(ZaprosuError, match="output_limit_exceeded"):
        await provider.chat_completion(token="secret-key", model="cheap-cn", prompt="test", max_output_tokens=5000)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(401,"authentication_rejected"),(403,"authentication_rejected"),(402,"balance_unavailable"),(429,"rate_limited"),(500,"upstream_unavailable"),(400,"model_or_channel_rejected"),(302,"redirect_rejected")])
async def test_status_codes_hide_upstream_body(monkeypatch, status, code):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    _Client.response = _response(status, b"private-key private-document")
    with pytest.raises(provider.ZaprosuError) as error:
        await provider.list_models("private-key")
    assert error.value.code == code
    assert "private-key" not in str(error.value)


@pytest.mark.asyncio
async def test_documented_channel_and_balance_codes_are_classified_without_body(monkeypatch):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    for upstream, expected in (("get_channel_failed", "channel_unavailable"), ("insufficient_balance", "balance_unavailable"), ("model_not_found", "model_unavailable")):
        _Client.response = _response(400, json.dumps({"error": {"code": upstream, "message": "private-document"}}).encode())
        with pytest.raises(provider.ZaprosuError) as error:
            await provider.list_models("private-key")
        assert error.value.code == expected
        assert "private-document" not in str(error.value)


@pytest.mark.asyncio
async def test_malformed_and_oversized_responses(monkeypatch):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    _Client.response = _response(200, b"not-json")
    with pytest.raises(provider.ZaprosuError, match="invalid_response"):
        await provider.list_models("secret-key")
    monkeypatch.setattr(provider, "MAX_RESPONSE_BYTES", 5)
    _Client.response = _response(200, b"123456")
    with pytest.raises(provider.ZaprosuError, match="response_too_large"):
        await provider.list_models("secret-key")


@pytest.mark.asyncio
async def test_timeout_is_sanitized(monkeypatch):
    class TimeoutClient(_Client):
        async def send(self, request, **_):
            raise httpx.ReadTimeout("private-key private-document")
    monkeypatch.setattr(provider.httpx, "AsyncClient", TimeoutClient)
    with pytest.raises(provider.ZaprosuError) as error:
        await provider.list_models("private-key")
    assert error.value.code == "timeout"
    assert error.value.retryable is True
    assert "private-key" not in str(error.value)


ZaprosuError = provider.ZaprosuError
