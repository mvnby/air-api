from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from core.config import Settings, settings
from services.client_address_service import ClientAddressService


REPO_ROOT = Path(__file__).resolve().parents[2]


def _proxy_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/")
    async def client_address(request: Request):
        return JSONResponse({"host": request.client.host})

    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=settings.proxy_trusted_hosts,
    )
    return app


def test_client_address_normalizes_ip_and_rejects_non_ip_values() -> None:
    assert ClientAddressService.normalize("2001:0db8::0001") == "2001:db8::/64"
    assert ClientAddressService.normalize("2001:db8::ffff") == "2001:db8::/64"
    assert ClientAddressService.normalize("2001:db8:0:1::1") == "2001:db8:0:1::/64"
    assert ClientAddressService.normalize(" 192.0.2.9 ") == "192.0.2.9"
    assert ClientAddressService.normalize("attacker-controlled") == "unavailable"
    assert ClientAddressService.normalize(None) == "unavailable"


@pytest.mark.parametrize(
    "trusted_hosts",
    ["*", "", "proxy.internal", "0.0.0.0/0", "::/0"],
)
def test_proxy_trust_configuration_rejects_unsafe_values(trusted_hosts) -> None:
    with pytest.raises(ValidationError):
        Settings(
            SECRET_KEY="test-only-secret-key-at-least-32-bytes-long",
            ADMIN_USERNAME="test-admin",
            ADMIN_PASSWORD="test-password",
            PROXY_TRUSTED_HOSTS=trusted_hosts,
            _env_file=None,
        )


def test_proxy_trust_configuration_canonicalizes_networks() -> None:
    configured = Settings(
        SECRET_KEY="test-only-secret-key-at-least-32-bytes-long",
        ADMIN_USERNAME="test-admin",
        ADMIN_PASSWORD="test-password",
        PROXY_TRUSTED_HOSTS="172.16.1.9/12,2001:0db8::0001/64",
        _env_file=None,
    )

    assert configured.proxy_trusted_hosts == ["172.16.0.0/12", "2001:db8::/64"]


def test_container_disables_uvicorns_duplicate_proxy_parser() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert '"--no-proxy-headers"' in dockerfile


@pytest.mark.asyncio
async def test_untrusted_peer_cannot_spoof_forwarded_client_address() -> None:
    transport = ASGITransport(app=_proxy_test_app(), client=("203.0.113.10", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/",
            headers={"X-Forwarded-For": "198.51.100.99"},
        )

    assert response.json() == {"host": "203.0.113.10"}


@pytest.mark.asyncio
async def test_trusted_proxy_selects_nearest_untrusted_forwarded_address() -> None:
    transport = ASGITransport(app=_proxy_test_app(), client=("172.18.0.5", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/",
            headers={"X-Forwarded-For": "198.51.100.99, 203.0.113.44"},
        )

    assert response.json() == {"host": "203.0.113.44"}


@pytest.mark.asyncio
async def test_trusted_proxy_skips_cloudflare_edge_to_select_client() -> None:
    transport = ASGITransport(app=_proxy_test_app(), client=("172.18.0.5", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/",
            headers={"X-Forwarded-For": "198.51.100.99, 173.245.48.10"},
        )

    assert response.json() == {"host": "198.51.100.99"}
