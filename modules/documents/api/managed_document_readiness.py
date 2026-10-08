"""Read-only requirements for one selected native contract/invoice/act action."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.customer_readiness import (
    check_selection_readiness,
    check_saved_document_readiness,
)
from modules.documents.application.errors import (
    ManagedDocumentNotFoundError,
    ManagedDocumentConflictError,
    ManagedDocumentError,
)
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from routers.manager_operation_ids import (
    CHECK_MANAGER_MANAGED_DOCUMENT_READINESS,
    GET_MANAGER_MANAGED_DOCUMENT_READINESS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from .draft_selection import selection_from_payload
from .schemas import (
    ManagedDocumentDraftPayload,
    ManagedDocumentReadinessResponse,
    DocumentCustomerReadiness,
)

router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.post(
    "/orders/{order_id}/documents/readiness",
    response_model=ManagedDocumentReadinessResponse,
    operation_id=CHECK_MANAGER_MANAGED_DOCUMENT_READINESS,
)
async def check_managed_document_readiness(
    order_id: int,
    payload: ManagedDocumentDraftPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Read the selected native version and scoped order facts without creating a draft
    or reserving a number. Reports only applicable placeholders surviving the frozen
    party conditions. Creating a draft and issuing it repeat server-side checks;
    this response is advisory and does not authorize issuance. Returns 404 for
    scoped dependencies, 409 for incompatible context, 400 for invalid facts and
    503 for unavailable private template bytes. Manager membership is required.
    """
    from .router import get_private_attachment_storage

    try:
        return await check_selection_readiness(
            session,
            tenant_scope=auth.tenant_scope(),
            selection=selection_from_payload(order_id, payload),
            template_id=payload.template_id,
            template_storage=PrivateTemplateSourceStorage(
                get_private_attachment_storage()
            ),
        )
    except ManagedDocumentNotFoundError as exc:
        raise _error(404, "managed_document_dependency_not_found", exc)
    except ManagedDocumentConflictError as exc:
        raise _error(409, "managed_document_conflict", exc)
    except OSError as exc:
        raise _error(503, "managed_document_template_unavailable", exc)
    except (ManagedDocumentError, TypeError, ValueError) as exc:
        raise _error(400, "managed_document_invalid", exc)


def _error(status, code, exc, endpoint=CHECK_MANAGER_MANAGED_DOCUMENT_READINESS):
    return manager_http_error(
        status_code=status, endpoint=endpoint, error_code=code, message=str(exc)
    )


@router.get(
    "/documents/{document_id}/readiness",
    response_model=DocumentCustomerReadiness,
    operation_id=GET_MANAGER_MANAGED_DOCUMENT_READINESS,
)
async def get_managed_document_readiness(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Check a scoped draft's persisted facts against its frozen native template.

    Reads source bytes without refreshing the snapshot or calling an edit provider.
    Issued documents are not rechecked. Missing/inaccessible documents return 404,
    incompatible context 409, unavailable source 503 and invalid snapshot 400.
    Manager membership is required. The issuance service repeats this check.
    """
    from .router import get_private_attachment_storage
    from modules.documents.application.lifecycle_service import ManagedDocumentService

    try:
        document = await ManagedDocumentService.get_document(
            session, tenant_scope=auth.tenant_scope(), document_id=document_id
        )
        return await check_saved_document_readiness(
            session,
            tenant_scope=auth.tenant_scope(),
            document=document,
            template_storage=PrivateTemplateSourceStorage(
                get_private_attachment_storage()
            ),
        )
    except ManagedDocumentNotFoundError as exc:
        raise _error(
            404,
            "managed_document_not_found",
            exc,
            GET_MANAGER_MANAGED_DOCUMENT_READINESS,
        )
    except ManagedDocumentConflictError as exc:
        raise _error(
            409,
            "managed_document_conflict",
            exc,
            GET_MANAGER_MANAGED_DOCUMENT_READINESS,
        )
    except OSError as exc:
        raise _error(
            503,
            "managed_document_template_unavailable",
            exc,
            GET_MANAGER_MANAGED_DOCUMENT_READINESS,
        )
    except (ManagedDocumentError, TypeError, ValueError) as exc:
        raise _error(
            400, "managed_document_invalid", exc, GET_MANAGER_MANAGED_DOCUMENT_READINESS
        )
