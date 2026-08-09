import ipaddress

import httpx
import pytest

from services.manager_content_source_service import (
    ManagerContentSourceError,
    ManagerContentSourceService,
)


def _client_factory(handler):
    transport = httpx.MockTransport(handler)
    return lambda: httpx.AsyncClient(transport=transport, follow_redirects=False)


@pytest.mark.asyncio
async def test_source_fetch_pins_request_to_validated_ip_and_extracts_readable_html():
    resolved: list[tuple[str, int]] = []

    async def resolver(hostname: str, port: int):
        resolved.append((hostname, port))
        return [ipaddress.ip_address("93.184.216.34")]

    def handler(request: httpx.Request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "vendor.example"
        assert request.headers["accept-encoding"] == "identity"
        assert request.extensions["sni_hostname"] == "vendor.example"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=(
                "<html><head><title>Серия ERA</title><script>ignore me</script>"
                "<style>.secret{display:none}</style></head>"
                "<body><nav>Меню</nav><main><h1>ERA</h1><p>Тихая работа.</p>"
                "<button>Купить</button></main><footer>Телефон</footer></body></html>"
            ).encode(),
            request=request,
        )

    service = ManagerContentSourceService(
        resolver=resolver,
        client_factory=_client_factory(handler),
    )
    result = await service.fetch("https://vendor.example/series?item=era#ignored")

    assert resolved == [("vendor.example", 443)]
    assert result.final_url == "https://vendor.example/series?item=era"
    assert result.title == "Серия ERA"
    assert result.text == "ERA\nТихая работа."
    assert "ignore me" not in result.text
    assert "display:none" not in result.text
    assert "Купить" not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.1.1", "224.0.0.1", "192.0.2.1", "::1"],
)
async def test_source_fetch_blocks_non_public_dns_targets_before_http(address: str):
    called = False

    async def resolver(_hostname: str, _port: int):
        return [ipaddress.ip_address(address)]

    def handler(_request: httpx.Request):
        nonlocal called
        called = True
        return httpx.Response(200)

    service = ManagerContentSourceService(
        resolver=resolver,
        client_factory=_client_factory(handler),
    )
    with pytest.raises(ManagerContentSourceError) as raised:
        await service.fetch("https://vendor.example/")

    assert raised.value.code == "blocked_address"
    assert called is False


@pytest.mark.asyncio
async def test_source_fetch_revalidates_redirect_and_blocks_private_destination():
    requested_hosts: list[str] = []

    async def resolver(hostname: str, _port: int):
        if hostname == "vendor.example":
            return [ipaddress.ip_address("93.184.216.34")]
        return [ipaddress.ip_address("10.0.0.9")]

    def handler(request: httpx.Request):
        requested_hosts.append(request.headers["host"])
        return httpx.Response(
            302,
            headers={"location": "http://internal.example/admin"},
            request=request,
        )

    service = ManagerContentSourceService(
        resolver=resolver,
        client_factory=_client_factory(handler),
    )
    with pytest.raises(ManagerContentSourceError) as raised:
        await service.fetch("https://vendor.example/")

    assert raised.value.code == "blocked_address"
    assert requested_hosts == ["vendor.example"]


@pytest.mark.asyncio
async def test_source_fetch_rejects_decompressed_body_over_size_limit():
    async def resolver(_hostname: str, _port: int):
        return [ipaddress.ip_address("93.184.216.34")]

    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"x" * 65,
            request=request,
        )

    service = ManagerContentSourceService(
        resolver=resolver,
        client_factory=_client_factory(handler),
    )
    service.MAX_RESPONSE_BYTES = 64

    with pytest.raises(ManagerContentSourceError) as raised:
        await service.fetch("https://vendor.example/")

    assert raised.value.code == "source_too_large"


@pytest.mark.asyncio
async def test_source_fetch_rejects_compressed_response_before_decompression():
    async def resolver(_hostname: str, _port: int):
        return [ipaddress.ip_address("93.184.216.34")]

    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-encoding": "gzip"},
            content=b"",
            request=request,
        )

    service = ManagerContentSourceService(
        resolver=resolver,
        client_factory=_client_factory(handler),
    )
    with pytest.raises(ManagerContentSourceError) as raised:
        await service.fetch("https://vendor.example/")

    assert raised.value.code == "unsupported_content_encoding"


@pytest.mark.asyncio
async def test_source_fetch_rejects_mixed_public_and_private_dns_answers():
    async def resolver(_hostname: str, _port: int):
        return [ipaddress.ip_address("93.184.216.34"), ipaddress.ip_address("127.0.0.1")]

    service = ManagerContentSourceService(
        resolver=resolver,
        client_factory=_client_factory(lambda _request: httpx.Response(500)),
    )

    with pytest.raises(ManagerContentSourceError) as raised:
        await service.fetch("https://vendor.example/")

    assert raised.value.code == "blocked_address"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/",
        "http://user:pass@example.com/",
        "http://example.com:8080/",
    ],
)
def test_source_url_policy_rejects_unsafe_forms(url: str):
    with pytest.raises(ManagerContentSourceError):
        ManagerContentSourceService._normalize_url(url)


def test_source_url_policy_maps_legacy_ipv4_host_to_typed_invalid_url():
    with pytest.raises(ManagerContentSourceError) as raised:
        ManagerContentSourceService._normalize_url("http://0177.0.0.1/")

    assert raised.value.code == "invalid_url"
