from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access, require_owner_access
from modules.documents.api import facsimiles
from modules.documents.application.facsimile_pdf import FacsimilePdfError

BASE = '/api/manager/document-system'


@pytest.fixture
async def facsimile_client(monkeypatch):
    app = FastAPI()
    app.include_router(facsimiles.router)
    auth = AuthenticatedUser(username='tenant-owner', auth_source='staff_password',
                             role='owner', tenant_id=21, storefront_id=71)
    app.dependency_overrides[require_manager_access] = lambda: auth
    app.dependency_overrides[require_owner_access] = lambda: auth
    session = AsyncMock()

    async def get_test_session():
        yield session

    app.dependency_overrides[get_session] = get_test_session
    monkeypatch.setattr(facsimiles, 'get_private_attachment_storage', lambda: object())
    monkeypatch.setattr(facsimiles, 'PrivateDocumentArtifactStorage', lambda storage: storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client, session


@pytest.mark.asyncio
async def test_prepare_facsimile_reports_missing_placement_as_conflict(facsimile_client, monkeypatch):
    client, _ = facsimile_client
    message = 'Для версии шаблона не задано размещение подписи и печати'
    prepare = AsyncMock(side_effect=FacsimilePdfError(message))
    monkeypatch.setattr(facsimiles.FacsimilePdfService, 'prepare', prepare)

    response = await client.post(f'{BASE}/documents/741/facsimile-pdf')

    assert response.status_code == 409
    assert response.json()['detail'] == {
        'message': message, 'error_code': 'document_facsimile_pdf_unavailable', 'field_errors': {},
    }
    assert prepare.await_args.kwargs['tenant_scope'].tenant_id == 21


@pytest.mark.asyncio
async def test_prepare_facsimile_returns_created_artifact(facsimile_client, monkeypatch):
    client, _ = facsimile_client
    monkeypatch.setattr(facsimiles.FacsimilePdfService, 'prepare', AsyncMock(return_value=
        SimpleNamespace(id='signed-artifact', kind='signed_pdf', filename='act-signed.pdf')))

    response = await client.post(f'{BASE}/documents/741/facsimile-pdf')

    assert response.status_code == 200
    assert response.json() == {'id': 'signed-artifact', 'kind': 'signed_pdf', 'filename': 'act-signed.pdf'}


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path,body,code', [
    ('GET', '/templates/8/versions/166/facsimile-placement', None, 'document_facsimile_placement_not_found'),
    ('PUT', '/templates/8/versions/166/facsimile-placement', {
        'page_number': 1, 'signature_x_mm': 20, 'signature_y_mm': 20, 'signature_width_mm': 40,
        'seal_x_mm': 80, 'seal_y_mm': 20, 'seal_width_mm': 30,
    }, 'native_template_version_not_found'),
    ('POST', '/legal-entities/1/facsimiles/signature', None, 'document_legal_entity_not_found'),
])
async def test_missing_facsimile_settings_return_404(facsimile_client, method, path, body, code):
    client, session = facsimile_client
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
    kwargs = {'json': body} if body is not None else {}
    if method == 'POST':
        kwargs = {'files': {'file': ('signature.png', b'png', 'image/png')}}

    response = await client.request(method, BASE + path, **kwargs)

    assert response.status_code == 404
    assert response.json()['detail']['error_code'] == code


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,content,code', [
    ('unknown', b'png', 'document_facsimile_kind_invalid'),
    ('signature', b'', 'document_facsimile_file_invalid'),
    ('seal', b'not-a-png', 'document_facsimile_file_invalid'),
])
async def test_invalid_facsimile_upload_returns_400(facsimile_client, kind, content, code):
    client, session = facsimile_client
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: object())

    response = await client.post(f'{BASE}/legal-entities/1/facsimiles/{kind}',
                                 files={'file': ('signature.png', content, 'image/png')})

    assert response.status_code == 400
    assert response.json()['detail']['error_code'] == code


def _visual_payload(**changes):
    return {
        'source_checksum_sha256': 'a' * 64, 'expected_signed_artifact_id': None,
        'signature_asset_id': 'b' * 32, 'seal_asset_id': 'c' * 32,
        'signature': {'page_number': 1, 'x_mm': 20, 'y_mm': 30, 'width_mm': 45},
        'seal': {'page_number': 2, 'x_mm': 80, 'y_mm': 40, 'width_mm': 35},
        **changes,
    }


@pytest.mark.asyncio
async def test_visual_preparation_receives_positions_and_actor(facsimile_client, monkeypatch):
    client, _ = facsimile_client
    prepare = AsyncMock(return_value=SimpleNamespace(id='copy', kind='signed_pdf', filename='copy.pdf'))
    monkeypatch.setattr(facsimiles.FacsimilePdfService, 'prepare', prepare)

    response = await client.post(f'{BASE}/documents/741/facsimile-pdf', json=_visual_payload())

    assert response.status_code == 200
    values = prepare.await_args.kwargs
    assert values['placement'].signature.page_number == 1
    assert values['placement'].seal.page_number == 2
    assert values['placement'].source_checksum_sha256 == 'a' * 64
    assert values['actor_username'] == 'tenant-owner'
    assert values['tenant_scope'].storefront_id == 71


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [
    {'signature': {'page_number': 1, 'x_mm': -1, 'y_mm': 1, 'width_mm': 45}},
    {'seal': {'page_number': 101, 'x_mm': 1, 'y_mm': 1, 'width_mm': 35}},
    {'source_checksum_sha256': 'invalid'},
    {'unexpected': True},
])
async def test_visual_preparation_rejects_invalid_input(facsimile_client, change):
    client, _ = facsimile_client
    response = await client.post(f'{BASE}/documents/741/facsimile-pdf', json=_visual_payload(**change))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_preview_returns_private_metadata(facsimile_client, monkeypatch):
    client, _ = facsimile_client
    response_data = {
        'document_id': 741, 'source_checksum_sha256': 'a' * 64,
        'signed_artifact_id': None, 'can_save': True,
        'pages': [{'page_number': 1, 'width_mm': 210, 'height_mm': 297}],
        'signature': {'asset_id': 'b' * 32, 'width_px': 100, 'height_px': 50},
        'seal': {'asset_id': 'c' * 32, 'width_px': 100, 'height_px': 100},
        'placement': {kind: _visual_payload()[kind] for kind in ('signature', 'seal')},
    }
    describe = AsyncMock(return_value=response_data)
    monkeypatch.setattr(facsimiles.FacsimilePreviewService, 'describe', describe)

    response = await client.get(f'{BASE}/documents/741/facsimile-preview')

    assert response.status_code == 200
    assert response.json() == response_data
    assert response.headers['cache-control'] == 'private, no-store'
    assert describe.await_args.kwargs['tenant_scope'].tenant_id == 21


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix,method', [('pages/1', 'page'), ('assets/' + 'b' * 32, 'asset')])
async def test_preview_pngs_are_authenticated_and_not_cached(facsimile_client, monkeypatch, suffix, method):
    client, _ = facsimile_client
    handler = AsyncMock(return_value=b'private-png')
    monkeypatch.setattr(facsimiles.FacsimilePreviewService, method, handler)
    response = await client.get(f'{BASE}/documents/741/facsimile-preview/{suffix}')
    assert response.status_code == 200
    assert response.content == b'private-png'
    assert response.headers['content-type'] == 'image/png'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert handler.await_args.kwargs['tenant_scope'].storefront_id == 71


@pytest.mark.asyncio
async def test_preview_conflicts_explain_missing_assets(facsimile_client, monkeypatch):
    client, _ = facsimile_client
    monkeypatch.setattr(facsimiles.FacsimilePreviewService, 'describe',
                        AsyncMock(side_effect=FacsimilePdfError('Загрузите PNG подписи и печати')))
    response = await client.get(f'{BASE}/documents/741/facsimile-preview')
    assert response.status_code == 409
    assert response.json()['detail']['message'] == 'Загрузите PNG подписи и печати'
