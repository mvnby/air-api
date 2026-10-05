import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from services import jev_provider_service as provider


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


class _Client:
    response = None
    request = None
    kwargs = None

    def __init__(self, **kwargs):
        type(self).kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, **_):
        type(self).request = request
        return type(self).response


def _payload(*, kind="customer_request", hvac=0.91):
    probabilities = {choice: 0.0 for choice in provider._KINDS}
    probabilities[kind] = 1.0
    return {
        "model": provider.JEV_MODEL,
        "answers": {
            "kind": {
                "type": "choice",
                "choice": kind,
                "probabilities": probabilities,
                "confidence": 0.98,
            },
            "hvac_demand": {"type": "noul", "noul": hvac},
        },
        "usage": {"input_tokens": 1000, "output_tokens": 21},
    }


def _response(status, body, **headers):
    return httpx.Response(
        status,
        headers=headers,
        stream=_ChunkStream(body),
        request=httpx.Request("POST", provider.JEV_ENDPOINT),
    )


@pytest.mark.asyncio
async def test_classify_payload_validation_result_cost_and_order(monkeypatch):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    _Client.response = _response(200, json.dumps(_payload()).encode())

    result = await provider.classify_jev(token="secret-token", state="Нужен расчет установки кондиционера")

    assert result.model == provider.JEV_MODEL
    assert result.kind == "customer_request"
    assert result.kind_confidence == 0.98
    assert result.hvac_probability == 0.91
    assert result.input_tokens == 1000 and result.output_tokens == 21
    assert result.duration_ms >= 0
    assert result.estimated_usd == Decimal("0.000042")
    assert result.is_potential_order is True
    assert _Client.request.url == provider.JEV_ENDPOINT
    assert _Client.request.headers["authorization"] == "Bearer secret-token"
    assert _Client.kwargs["timeout"] == provider._HTTP_TIMEOUT_SECONDS
    assert _Client.kwargs["trust_env"] is False
    assert _Client.kwargs["follow_redirects"] is False
    sent = json.loads(_Client.request.content)
    assert sent["model"] == "jev-1.13.0"
    assert sent["state"] == "Нужен расчет установки кондиционера"
    assert set(sent["questions"]["kind"]["criteria"]) == set(provider._KINDS)
    assert "untrusted" in sent["questions"]["kind"]["instructions"]
    assert "сломался кондиционер" in sent["questions"]["hvac_demand"]["instructions"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,hvac,expected",
    [
        ("tender", 0.8, True),
        ("service", 0.5, True),
        ("supplier_offer", 0.99, False),
        ("advertising", 0.7, False),
        ("other", 1.0, False),
        ("customer_request", 0.49, False),
    ],
)
async def test_potential_order_requires_kind_and_demand(monkeypatch, kind, hvac, expected):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    _Client.response = _response(200, json.dumps(_payload(kind=kind, hvac=hvac)).encode())
    result = await provider.classify_jev(token="secret-token", state="message")
    assert result.is_potential_order is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (401, "authentication_rejected"),
        (403, "authentication_rejected"),
        (429, "rate_limited"),
        (500, "provider_unavailable"),
        (529, "provider_unavailable"),
        (422, "provider_rejected"),
        (302, "redirect_rejected"),
    ],
)
async def test_http_failures_are_sanitized_and_redirects_are_not_followed(monkeypatch, status, code):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    _Client.response = _response(status, b"secret-token raw private state")
    with pytest.raises(provider.JevProviderError) as error:
        await provider.classify_jev(token="secret-token", state="raw private state")

    assert error.value.code == code
    assert error.value.status == status
    assert "secret-token" not in str(error.value)
    assert "private state" not in str(error.value)
    assert _Client.kwargs["follow_redirects"] is False


def _malformed_response(which):
    data = _payload()
    if which == "wrong_model":
        data["model"] = "jev-latest"
    elif which == "missing_answer":
        del data["answers"]["kind"]
    elif which == "extra_answer":
        data["answers"]["extra"] = {}
    elif which == "invalid_choice":
        data["answers"]["kind"]["choice"] = "buyer"
    elif which == "missing_probability_key":
        del data["answers"]["kind"]["probabilities"]["other"]
    elif which == "probability_sum":
        data["answers"]["kind"]["probabilities"]["other"] = 0.5
    elif which == "nan_probability":
        data["answers"]["kind"]["confidence"] = float("nan")
    elif which == "boolean_probability":
        data["answers"]["hvac_demand"]["noul"] = True
    elif which == "negative_usage":
        data["usage"]["output_tokens"] = -1
    elif which == "boolean_usage":
        data["usage"]["input_tokens"] = True
    elif which == "too_many_input_tokens":
        data["usage"]["input_tokens"] = 64001
    return data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed",
    [
        "wrong_model",
        "missing_answer",
        "extra_answer",
        "invalid_choice",
        "missing_probability_key",
        "probability_sum",
        "nan_probability",
        "boolean_probability",
        "negative_usage",
        "boolean_usage",
        "too_many_input_tokens",
    ],
)
async def test_rejects_malformed_answers_usage_and_model(monkeypatch, malformed):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    body = json.dumps(_malformed_response(malformed), allow_nan=True).encode()
    _Client.response = _response(200, body)
    with pytest.raises(provider.JevProviderError) as error:
        await provider.classify_jev(token="secret-token", state="message")
    assert error.value.code == "invalid_response"


@pytest.mark.asyncio
async def test_rejects_blank_or_oversized_input_before_network(monkeypatch):
    class UnusedClient(_Client):
        def __init__(self, **_):
            raise AssertionError("network client must not be created for invalid input")

    monkeypatch.setattr(provider.httpx, "AsyncClient", UnusedClient)
    for token, state, code in [
        ("  ", "message", "invalid_credential"),
        ("secret-token", "  ", "invalid_input"),
        ("secret-token", "x" * (provider.JEV_MAX_STATE_CHARS + 1), "input_too_large"),
    ]:
        with pytest.raises(provider.JevProviderError) as error:
            await provider.classify_jev(token=token, state=state)
        assert error.value.code == code
        if token.strip():
            assert token.strip() not in str(error.value)


@pytest.mark.asyncio
async def test_rejects_invalid_json_and_response_size(monkeypatch):
    monkeypatch.setattr(provider.httpx, "AsyncClient", _Client)
    _Client.response = _response(200, b"not json")
    with pytest.raises(provider.JevProviderError, match="invalid_response"):
        await provider.classify_jev(token="secret-token", state="message")

    monkeypatch.setattr(provider, "MAX_RESPONSE_BYTES", 10)
    _Client.response = _response(200, b"12345678901")
    with pytest.raises(provider.JevProviderError, match="response_too_large"):
        await provider.classify_jev(token="secret-token", state="message")

    _Client.response = _response(200, b"{}", **{"content-length": str(provider.MAX_RESPONSE_BYTES + 1)})
    with pytest.raises(provider.JevProviderError, match="response_too_large"):
        await provider.classify_jev(token="secret-token", state="message")


@pytest.mark.asyncio
async def test_request_deadline_includes_provider_wait_and_hides_exception(monkeypatch):
    class SlowClient(_Client):
        async def send(self, request, **_):
            await asyncio.sleep(0.1)

    monkeypatch.setattr(provider.httpx, "AsyncClient", SlowClient)
    monkeypatch.setattr(provider, "_REQUEST_DEADLINE_SECONDS", 0.01)
    with pytest.raises(provider.JevProviderError) as error:
        await provider.classify_jev(token="secret-token", state="private state")
    assert error.value.code == "timeout"
    assert "secret-token" not in str(error.value)
    assert "private state" not in str(error.value)


@pytest.mark.asyncio
async def test_transport_errors_do_not_expose_exception_details(monkeypatch):
    class BrokenClient(_Client):
        async def send(self, request, **_):
            raise httpx.ReadError("secret-token and private state")

    monkeypatch.setattr(provider.httpx, "AsyncClient", BrokenClient)
    with pytest.raises(provider.JevProviderError) as error:
        await provider.classify_jev(token="secret-token", state="private state")
    assert error.value.code == "provider_unavailable"
    assert "secret-token" not in str(error.value)
    assert "private state" not in str(error.value)
