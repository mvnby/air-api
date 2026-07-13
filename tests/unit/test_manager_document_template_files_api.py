import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.security import get_current_username
from routers.manager_docs import (
    DOCUMENT_TEMPLATE_FILES_UNAVAILABLE,
    DOCUMENT_TEMPLATE_FILES_UNAVAILABLE_MESSAGE,
    router as manager_docs_router,
)
from services.google_oauth_credentials import (
    GoogleDriveListError,
    GoogleTokenRefreshError,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "google_error",
    [
        GoogleTokenRefreshError("provider-secret-auth-error"),
        GoogleDriveListError("provider-secret-drive-error"),
    ],
    ids=["oauth", "drive"],
)
async def test_document_template_files_maps_google_failures_to_controlled_502(
    monkeypatch,
    google_error,
):
    class _FailingGoogleService:
        def list_files(self, _folder_id: str, *, limit: int):
            raise google_error

    monkeypatch.setattr(
        "routers.manager_docs.get_google_service",
        lambda: _FailingGoogleService(),
    )
    app = FastAPI()
    app.include_router(manager_docs_router)
    app.dependency_overrides[get_current_username] = lambda: "admin"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/manager/docs/document-template-files",
            params={"folder_id": "templates", "limit": 25},
        )

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "message": DOCUMENT_TEMPLATE_FILES_UNAVAILABLE_MESSAGE,
            "error_code": DOCUMENT_TEMPLATE_FILES_UNAVAILABLE,
            "field_errors": {},
        }
    }
    assert "provider-secret" not in response.text
