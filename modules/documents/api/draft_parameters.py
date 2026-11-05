"""Manager commands for parameters of an existing unissued document."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.draft_mutations import (
    ManagedDocumentDraftMutationService,
)
from modules.documents.application.errors import (
    ManagedDocumentConflictError,
    ManagedDocumentNotFoundError,
)
from routers.manager_operation_ids import (
    GET_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
    UPDATE_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from .draft_parameter_schemas import (
    ManagedDocumentDraftParameters,
    ManagedDocumentDraftParameterUpdate,
)
from .managed_documents_artifacts import _document_error, _document_item
from .schemas import ManagedDocumentItem

router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/documents/{document_id}/draft/parameters",
    response_model=ManagedDocumentDraftParameters,
    operation_id=GET_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
)
async def get_draft_parameters(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentDraftParameters:
    """Read saved parameters and revision of a tenant/storefront-scoped unnumbered draft.

    Missing documents return 404; issued/reserved documents return 409. Reading does not
    refresh facts from live CRM data or change files. Requires authenticated Manager access.
    """
    try:
        return ManagedDocumentDraftParameters.model_validate(
            await ManagedDocumentDraftMutationService.get(
                session, tenant_scope=auth.tenant_scope(), document_id=document_id
            )
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404,
            GET_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
            "managed_document_not_found",
            exc,
        )
    except (ManagedDocumentConflictError, ValueError) as exc:
        raise _document_error(
            409,
            GET_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
            "managed_document_draft_conflict",
            exc,
        )


@router.patch(
    "/documents/{document_id}/draft/parameters",
    response_model=ManagedDocumentItem,
    operation_id=UPDATE_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
)
async def update_draft_parameters(
    document_id: int,
    payload: ManagedDocumentDraftParameterUpdate,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentItem:
    """Save parameters on the same tenant/storefront-scoped draft without reserving a number.

    expected_revision prevents overwriting a concurrent edit. A date-only update preserves
    manual DOCX edits; other changes require reset_editable_copy when a working copy exists.
    Confirmed reset detaches old editor sessions; the next editor open creates a new copy.
    Pass template_version_id alone with the revision to apply an active DOCX version of
    the same template. This keeps frozen facts, rechecks requirements and uses the same
    explicit working-copy reset. Unavailable template storage returns 503.
    Term groups replace their saved group. Issued/reserved/closed drafts and stale revisions
    return 409, missing documents 404, incompatible terms 400. Requires Manager access.
    """
    try:
        if payload.template_version_id is not None:
            from .router import get_private_attachment_storage
            from modules.documents.infrastructure.template_source_storage import (
                PrivateTemplateSourceStorage,
            )

            row = await ManagedDocumentDraftMutationService.apply_template_version(
                session,
                tenant_scope=auth.tenant_scope(),
                document_id=document_id,
                version_id=payload.template_version_id,
                expected_revision=payload.expected_revision,
                reset_editable_copy=payload.reset_editable_copy,
                template_storage=PrivateTemplateSourceStorage(
                    get_private_attachment_storage()
                ),
            )
            return await _document_item(session, auth, row)
        changes = payload.model_dump(
            mode="json",
            exclude_unset=True,
            exclude={"expected_revision", "reset_editable_copy"},
        )
        row = await ManagedDocumentDraftMutationService.update(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            changes=changes,
            expected_revision=payload.expected_revision,
            reset_editable_copy=payload.reset_editable_copy,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404,
            UPDATE_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
            "managed_document_not_found",
            exc,
        )
    except ManagedDocumentConflictError as exc:
        raise _document_error(
            409,
            UPDATE_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
            "managed_document_draft_conflict",
            exc,
        )
    except OSError as exc:
        raise _document_error(
            503,
            UPDATE_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
            "managed_document_template_unavailable",
            exc,
        )
    except (TypeError, ValueError) as exc:
        raise _document_error(
            400,
            UPDATE_MANAGER_MANAGED_DOCUMENT_DRAFT_PARAMETERS,
            "managed_document_draft_invalid",
            exc,
        )
    return await _document_item(session, auth, row)
