"""Explicit Manager action for reviewing an original email contract attachment."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, get_current_manager_tenant_scope, require_system_manager_tenant_scope
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    DOWNLOAD_MANAGER_EMAIL_LEAD_ORIGINAL,
    LIST_MANAGER_EMAIL_LEAD_ORIGINALS,
    REVIEW_MANAGER_EMAIL_LEAD_CONTRACT,
    REVIEW_MANAGER_EMAIL_LEAD_ORIGINAL,
    GET_MANAGER_EMAIL_LEAD_CONTRACT_REVIEW_JOB,
)
from schemas_contract_review import ContractReviewJobResponse, OriginalEmailAttachmentItem, OriginalEmailAttachmentList
from services.deepseek_provider_service import DefectActAIProviderError
from services.email_contract_review_service import ContractReviewInputError, EmailContractReviewService
from services.email_contract_review_job_service import EmailContractReviewJobService
from services.email_lead_original_attachment_service import EmailLeadOriginalAttachmentService, OriginalEmailFile
from services.manager_content_ai_limiter import ManagerContentAIRateLimitError, manager_content_ai_limiter


router = APIRouter(prefix="/api/manager/leads", tags=["manager-leads-inbox"])


def _owner(auth: AuthenticatedUser) -> str:
    return f"{auth.tenant_id or 0}:{auth.username}"


@router.get(
    "/inbox/contract-review-jobs/{job_id}",
    response_model=ContractReviewJobResponse,
    operation_id=GET_MANAGER_EMAIL_LEAD_CONTRACT_REVIEW_JOB,
)
async def get_manager_email_lead_contract_review_job(
    job_id: str,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> ContractReviewJobResponse:
    job = await EmailContractReviewJobService.get(job_id=job_id, owner=_owner(auth))
    if job is None:
        raise HTTPException(status_code=404, detail="Проверка не найдена или срок хранения истёк")
    return job


async def _originals(session: AsyncSession, order_id: int, tenant_scope: TenantScope) -> list[OriginalEmailFile]:
    try:
        originals = await EmailLeadOriginalAttachmentService.load(
            session, order_id=order_id, tenant_scope=tenant_scope,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Почтовый оригинал сейчас недоступен") from exc
    if originals is None:
        raise HTTPException(status_code=404, detail="Оригинал письма не найден")
    return originals


@router.get(
    "/inbox/{order_id}/email-originals",
    response_model=OriginalEmailAttachmentList,
    operation_id=LIST_MANAGER_EMAIL_LEAD_ORIGINALS,
)
async def list_manager_email_lead_originals(
    order_id: int,
    _: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> OriginalEmailAttachmentList:
    originals = await _originals(session, order_id, tenant_scope)
    return OriginalEmailAttachmentList(items=[
        OriginalEmailAttachmentItem(
            position=item.position, filename=item.filename,
            size_bytes=len(item.content), content_type=item.content_type,
        ) for item in originals
    ])


@router.get(
    "/inbox/{order_id}/email-originals/{position}/download",
    operation_id=DOWNLOAD_MANAGER_EMAIL_LEAD_ORIGINAL,
)
async def download_manager_email_lead_original(
    order_id: int,
    position: int,
    _: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> Response:
    originals = await _originals(session, order_id, tenant_scope)
    item = next((candidate for candidate in originals if candidate.position == position), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Вложение не найдено")
    return Response(
        content=item.content, media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.filename, safe='')}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/inbox/{order_id}/email-originals/{position}/review",
    response_model=ContractReviewJobResponse,
    operation_id=REVIEW_MANAGER_EMAIL_LEAD_ORIGINAL,
    dependencies=[Depends(require_system_manager_tenant_scope)],
)
async def review_manager_email_lead_original(
    order_id: int,
    position: int,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> ContractReviewJobResponse:
    try:
        async with manager_content_ai_limiter.limit(_owner(auth)):
            originals = await _originals(session, order_id, tenant_scope)
            item = next((candidate for candidate in originals if candidate.position == position), None)
            if item is None:
                raise HTTPException(status_code=404, detail="Вложение не найдено")
            return await EmailContractReviewJobService.start(
                owner=_owner(auth), attachment_id=0, filename=item.filename, content=item.content,
            )
    except ManagerContentAIRateLimitError as exc:
        raise HTTPException(status_code=429, detail="Лимит проверок превышен; повторите позже", headers={"Retry-After": str(exc.retry_after)}) from exc
    except ContractReviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DefectActAIProviderError as exc:
        raise HTTPException(status_code=503 if exc.retryable else 502, detail="Проверка AI сейчас недоступна; попробуйте позже") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post(
    "/inbox/{order_id}/contract-review/{attachment_id}",
    response_model=ContractReviewJobResponse,
    operation_id=REVIEW_MANAGER_EMAIL_LEAD_CONTRACT,
    dependencies=[Depends(require_system_manager_tenant_scope)],
)
async def review_manager_email_lead_contract(
    order_id: int,
    attachment_id: int,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> ContractReviewJobResponse:
    try:
        async with manager_content_ai_limiter.limit(_owner(auth)):
            source = await EmailContractReviewService.load_content(
                session,
                order_id=order_id,
                attachment_id=attachment_id,
                tenant_scope=tenant_scope,
            )
            if source is None:
                raise HTTPException(status_code=404, detail="Email-вложение не найдено в этом обращении")
            filename, content = source
            return await EmailContractReviewJobService.start(
                owner=_owner(auth), attachment_id=attachment_id, filename=filename, content=content,
            )
    except ManagerContentAIRateLimitError as exc:
        raise HTTPException(status_code=429, detail="Лимит проверок превышен; повторите позже", headers={"Retry-After": str(exc.retry_after)}) from exc
    except ContractReviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DefectActAIProviderError as exc:
        raise HTTPException(status_code=503 if exc.retryable else 502, detail="Проверка AI сейчас недоступна; попробуйте позже") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
