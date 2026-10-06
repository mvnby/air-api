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
