"""Official fileParams shape and bounded, pinned ChatGPT photo source behavior."""
import socket
from contextlib import asynccontextmanager

import pytest

from core.config import settings
from schemas_connector_maintenance import OpenAIFile
from services.connector_file_service import ConnectorFileError, ConnectorFileService, _PinnedResolver
from services.connector_mcp_tools import TOOLS
from tests.integration.test_maintenance_observations_api import image_bytes


def file(**changes):
    return OpenAIFile(download_url=changes.pop('download_url', 'https://delivery.example/file-123?signature=secret'),
                      file_id='file-123', **changes)


def test_file_params_discovery_and_bounded_tools():
    assert len(TOOLS) == 28
    definition = TOOLS['upload_maintenance_finding_photo'].definition().model_dump(by_alias=True)
    assert definition['_meta']['openai/fileParams'] == ['file']
    schema = definition['inputSchema']['$defs']['OpenAIFile']
    assert set(schema['properties']) == {'download_url', 'file_id', 'mime_type', 'file_name'}
    assert set(schema['required']) == {'download_url', 'file_id'}
    assert schema['properties']['mime_type']['type'] == 'string'
    assert schema['properties']['file_name']['type'] == 'string'
    assert definition['annotations']['readOnlyHint'] is False
    assert definition['_meta']['securitySchemes'][0]['scopes'] == ['kitlane:read', 'kitlane:maintenance:write']
    assert not {'issue_maintenance_offer', 'accept_maintenance_offer', 'resolve_maintenance_finding'} & TOOLS.keys()


@pytest.mark.parametrize('url', [
    'http://delivery.example/photo', 'https://evil.example/photo', 'https://delivery.example.evil.example/photo',
    'https://user@delivery.example/photo', 'https://delivery.example:443/photo',
    'https://delivery.example/photo#fragment', 'https://127.0.0.1/photo', 'https://[::1]/photo',
    'https://delivery.example\\@evil.example/photo', 'https://delivery.example/pho\nto',
])
def test_untrusted_urls_fail_closed(monkeypatch, url):
    monkeypatch.setattr(settings, 'CONNECTOR_CHATGPT_FILE_HOSTS', ['delivery.example'])
    with pytest.raises(ConnectorFileError):
        ConnectorFileService.validate_source(file(download_url=url))


def test_empty_operator_host_evidence_blocks_upload(monkeypatch):
    monkeypatch.setattr(settings, 'CONNECTOR_CHATGPT_FILE_HOSTS', [])
    with pytest.raises(ConnectorFileError, match='not configured'):
        ConnectorFileService.validate_source(file())


@pytest.mark.asyncio
@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
async def test_private_dns_fails_before_fetch(monkeypatch, address):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 443))]
    monkeypatch.setattr('asyncio.BaseEventLoop.getaddrinfo', resolve)
    with pytest.raises(ConnectorFileError, match='public network'):
        await ConnectorFileService.public_addresses('delivery.example')


@pytest.mark.asyncio
async def test_pinned_resolver_cannot_resolve_another_destination():
    resolver = _PinnedResolver('delivery.example', ['8.8.8.8'])
    assert (await resolver.resolve('delivery.example', 443))[0]['host'] == '8.8.8.8'
    with pytest.raises(ConnectorFileError):
        await resolver.resolve('other.example', 443)
    with pytest.raises(ConnectorFileError):
        await resolver.resolve('delivery.example', 80)


@pytest.mark.asyncio
@pytest.mark.parametrize('status,body,mime,limit,expected', [
    (200, image_bytes(), 'image/png', 1024, None),
    (302, image_bytes(), 'image/png', 1024, 'unavailable'),
    (200, b'invalid-image', 'image/png', 1024, 'valid'),
    (200, image_bytes(), 'text/plain', 1024, 'match'),
    (200, image_bytes(), 'image/png', 1, 'size'),
])
async def test_download_disallows_redirects_and_bounds_verified_content(monkeypatch, status, body, mime, limit, expected):
    monkeypatch.setattr(settings, 'CONNECTOR_CHATGPT_FILE_HOSTS', ['delivery.example'])
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_MAX_SIZE_BYTES', limit)
    calls = []
    async def addresses(host):
        calls.append(host)
        return ['8.8.8.8']
    monkeypatch.setattr(ConnectorFileService, 'public_addresses', addresses)
    class Content:
        async def iter_chunked(self, size):
            yield body
    class Response:
        content = Content()
        content_length = None  # Streaming bound must work without Content-Length.
        headers = {'Content-Type': mime, 'Location': 'http://127.0.0.1/secret'}
    response = Response(); response.status = status
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False
            self.connector = kwargs['connector']
            assert self.connector._resolver.addresses == ['8.8.8.8']
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            await self.connector.close()
        @asynccontextmanager
        async def get(self, url, **kwargs):
            assert kwargs == {'allow_redirects': False}
            yield response
    monkeypatch.setattr('services.connector_file_service.aiohttp.ClientSession', Client)
    if expected:
        with pytest.raises(ConnectorFileError, match=expected):
            await ConnectorFileService.download(file())
    else:
        content, filename, kind = await ConnectorFileService.download(file())
        assert content == body and filename == 'file-123.png' and kind == 'image/png'
    assert calls == ['delivery.example']
