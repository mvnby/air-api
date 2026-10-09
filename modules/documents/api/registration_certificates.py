from urllib.parse import quote
from fastapi import APIRouter, Depends, File, UploadFile, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from core.manager_api_errors import manager_http_error
from models.legal_entity_attachment import LegalEntityAttachment
from services.legal_entity_attachment_service import (
    LegalEntityAttachmentService as Certificates,
    MAX_CERTIFICATE_BYTES,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from .registration_certificate_schemas import RegistrationCertificateItem

router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


def error(status, endpoint, exc):
    return manager_http_error(
        status_code=status,
        endpoint=endpoint,
        error_code="registration_certificate_invalid",
        message=str(exc),
    )


def require_writer(auth, endpoint):
    if auth.role not in {"owner", "admin"} or auth.demo_read_only:
        raise error(
            403,
            endpoint,
            "Загрузка и выбор свидетельства доступны владельцу и администратору",
        )


@router.get(
    "/legal-entities/{legal_entity_id}/registration-certificates",
    response_model=list[RegistrationCertificateItem],
    operation_id="list_manager_registration_certificates",
)
async def list_certificates(
    legal_entity_id: int,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """
    List private immutable registration certificate versions for a legal entity in the
    current tenant. Managers may read; foreign/missing issuers return 404. Limit is
    clamped to 1..100, current version first. Read only; no storage locations are exposed.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        await Certificates.entity(session, auth.tenant_id, legal_entity_id)
    except ValueError as exc:
        raise error(404, "list_manager_registration_certificates", exc)
    return (
        (
            await session.execute(
                select(LegalEntityAttachment)
                .where(
                    LegalEntityAttachment.tenant_id == auth.tenant_id,
                    LegalEntityAttachment.legal_entity_id == legal_entity_id,
                )
                .order_by(
                    LegalEntityAttachment.is_current.desc(),
                    LegalEntityAttachment.created_at.desc(),
                )
                .limit(max(1, min(limit, 100)))
            )
        )
        .scalars()
        .all()
    )


@router.post(
    "/legal-entities/{legal_entity_id}/registration-certificates",
    response_model=RegistrationCertificateItem,
    operation_id="upload_manager_registration_certificate",
)
async def upload_certificate(
    legal_entity_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """
    Owner/admin uploads a private registration certificate for an own-tenant legal entity
    and makes the new immutable version current. Actual PDF/JPEG/PNG is validated,
    including parser integrity; encrypted/empty PDF, invalid image, file over 10 MB or
    image over 20 million pixels returns 400. Missing/foreign entity returns 404,
    manager-only or demo writes return 403. Name is sanitized using the actual file type.
    Replacement never deletes previous bytes or mail metadata. Concurrent writes are
    serialized per issuer. No caller replay receipt: reload versions before repeating an
    upload after an uncertain response.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    endpoint = "upload_manager_registration_certificate"
    require_writer(auth, endpoint)
    try:
        await Certificates.entity(session, auth.tenant_id, legal_entity_id)
    except ValueError as exc:
        raise error(404, endpoint, exc)
    try:
        return await Certificates.upload(
            session,
            auth.tenant_id,
            legal_entity_id,
            await file.read(MAX_CERTIFICATE_BYTES + 1),
            file.filename,
        )
    except ValueError as exc:
        raise error(400, endpoint, exc)


@router.put(
    "/registration-certificates/{attachment_id}/current",
    response_model=RegistrationCertificateItem,
    operation_id="select_manager_registration_certificate",
)
async def select_certificate(
    attachment_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """
    Owner/admin selects an immutable registration certificate version owned by the current
    tenant as current for its original issuer, retaining every other version and earlier
    mail attachments. Missing/foreign version returns 404; manager-only or demo writes
    return 403. The issuer row serializes concurrent selection/replacement; repeating the
    same selection is safe and no mail is sent.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    endpoint = "select_manager_registration_certificate"
    require_writer(auth, endpoint)
    try:
        row = await Certificates.get(session, auth.tenant_id, attachment_id)
        return await Certificates.make_current(session, auth.tenant_id, row)
    except ValueError as exc:
        raise error(404, endpoint, exc)


@router.get(
    "/registration-certificates/{attachment_id}/download",
    operation_id="download_manager_registration_certificate",
)
async def download_certificate(
    attachment_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """
    Download an immutable private registration certificate owned by the current tenant.
    Managers can download current and historical versions; missing/foreign versions
    return 404 and unavailable or checksum-mismatched storage returns 409. Returns actual
    PDF/JPEG/PNG bytes with a safe original filename and private no-store cache headers.
    Storage keys and public media URLs are never exposed. Read only; retry is safe.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    endpoint = "download_manager_registration_certificate"
    try:
        row = await Certificates.get(session, auth.tenant_id, attachment_id)
    except ValueError as exc:
        raise error(404, endpoint, exc)
    try:
        content = await Certificates.read(row)
    except (ValueError, FileNotFoundError) as exc:
        raise error(409, endpoint, "Сохранённое свидетельство недоступно") from exc
    return Response(
        content,
        media_type=row.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
