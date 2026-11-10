"""Manager review surface over the shared template-audit application layer."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.database import get_session
from core.security import AuthenticatedUser, require_owner_access
from api_contracts.document_template_audits import (
    TemplateAuditDecisionInput,
    TemplateAuditPreviewInput,
    TemplateAuditPreviewContext,
    TemplateAuditReportResult,
    TemplateAuditReportList,
)
from modules.documents.application.template_audit_commands import TemplateAuditCommands
from modules.documents.application.template_audit_preview import (
    fictional_preview_context,
    render_proposal_preview,
)
from modules.documents.infrastructure.renderers.pdf import PdfConversionError
from routers.manager_permission_policy import ManagerPermissionRoute

router = APIRouter(
    prefix="/api/manager/document-system/template-audits",
    tags=["manager-document-system"],
    dependencies=[Depends(require_owner_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "",
    response_model=TemplateAuditReportList,
    operation_id="list_manager_template_audits",
)
async def list_template_audits(
    legal_entity_id: int = Query(gt=0),
    template_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
) -> dict:
    """Read bounded saved reports for the current company's issuer. Requires live owner/admin membership and customer applicability; inaccessible scope returns 404/403. Reports separate source coverage from legal evidence and recalculate staleness. Read-only; no generation or activation."""
    return await TemplateAuditCommands.list_reports(
        session, CommandActor.from_auth(auth), legal_entity_id, template_id, page, limit
    )


@router.get(
    "/{report_id}",
    response_model=TemplateAuditReportResult,
    operation_id="get_manager_template_audit",
)
async def get_template_audit(
    report_id: int,
    legal_sources_hash: str | None = Query(default=None, pattern="^[a-f0-9]{64}$"),
    occurrences_finding_id: str | None = Query(default=None, max_length=64),
    occurrences_page: int = Query(default=1, ge=1),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    """Read an exact saved template/version report with findings, decisions and inactive proposals. Requires live company owner/admin and current issuer/customer applicability. Foreign IDs return 404. Optional current legal evidence hash marks changed sources stale; absent hash requires external recheck. No writes."""
    return await TemplateAuditCommands.get(
        session,
        CommandActor.from_auth(auth),
        report_id,
        legal_sources_hash,
        occurrences_finding_id=occurrences_finding_id,
        occurrences_page=occurrences_page,
    )


@router.patch(
    "/{report_id}/findings/{finding_id}",
    response_model=TemplateAuditReportResult,
    operation_id="decide_manager_template_audit_finding",
)
async def decide_template_audit_finding(
    report_id: int,
    finding_id: str,
    payload: TemplateAuditDecisionInput,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    """Record a user's explicit Manager finding decision and reason, retaining its history. Live company owner/admin, exact report revision and source/context/legal evidence hashes are required. Stale writes return 409; reread after timeout before retrying. Never edits or activates a template."""
    return await TemplateAuditCommands.decide(
        session, CommandActor.from_auth(auth), report_id, finding_id, payload
    )


@router.get(
    "/{report_id}/proposals/{proposal_id}/preview-context",
    response_model=TemplateAuditPreviewContext,
    operation_id="get_manager_template_audit_preview_context",
)
async def get_preview_context(
    report_id: int,
    proposal_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    """Read an explicitly fictional editable test context for one inactive revision. Company owner/admin and unchanged source/context/legal evidence are required; foreign IDs return 404 and stale proposals 409. No real customer document, numbering, activation or other write is performed."""
    return await fictional_preview_context(
        session, CommandActor.from_auth(auth), report_id, proposal_id
    )


@router.post(
    "/{report_id}/proposals/{proposal_id}/preview",
    response_class=Response,
    operation_id="preview_manager_template_audit_proposal",
)
async def preview_template_audit_proposal(
    report_id: int,
    proposal_id: int,
    payload: TemplateAuditPreviewInput,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    """Render one saved inactive proposal to private DOCX/PDF on an explicitly selected fictional field/condition/table context. Requires live company owner/admin and matching source/context/legal evidence hashes. Missing fields return 400, stale data 409 and unavailable converter 503. Read-only: no CRM draft, official number, issued file or activation is changed. Repeat is safe."""
    from fastapi import HTTPException
    from modules.documents.api.router import _pdf_converter

    try:
        content = await render_proposal_preview(
            session,
            CommandActor.from_auth(auth),
            report_id,
            proposal_id,
            payload,
            pdf_converter=_pdf_converter(),
        )
    except PdfConversionError as exc:
        raise HTTPException(
            503, "PDF preview unavailable; download the fictional DOCX"
        ) from exc
    return Response(
        content,
        media_type="application/pdf"
        if payload.format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'inline; filename="template-audit-preview.{payload.format}"',
        },
    )
