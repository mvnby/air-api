from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST
from core.security import get_current_username
from routers.manager_operation_ids import (
    ATTACH_MANAGER_BANK_RECEIPT,
    ATTACH_MANAGER_BANK_RECEIPT_GROUP,
    DELETE_MANAGER_BANK_RECEIPT,
    IMPORT_MANAGER_BANK_RECEIPTS,
    IMPORT_MANAGER_BANK_STATEMENT,
    IMPORT_MANAGER_EMAIL_LEADS,
    GET_MANAGER_EMAIL_LEAD_IMPORT_STATUS,
    LIST_MANAGER_BANK_RECEIPTS,
    PATCH_MANAGER_BANK_RECEIPT_STATUS,
    SEND_MANAGER_ORDER_EMAIL,
    SEND_MANAGER_TEST_EMAIL,
)
from schemas import (
    BankReceiptAttachPayload,
    BankReceiptGroupAttachPayload,
    BankReceiptImportResponse,
    BankReceiptListResponse,
    BankReceiptResponse,
    BankReceiptStatusPayload,
    BankStatementImportResponse,
    EmailLeadDecisionResponse,
    EmailLeadImportJobResponse,
    EmailLeadImportResponse,
    OrderEmailSendPayload,
    OutgoingEmailResponse,
    OutgoingEmailSendPayload,
)
from services.bank_receipt_service import BankReceiptService
from services.bank_statement_csv_service import BankStatementCsvService
from services.email_lead_import_job_service import EmailLeadImportJobService, EmailLeadImportJobSnapshot
from services.mail_imap_service import MailImapService
from services.mail_smtp_service import MailSmtpService


router = APIRouter(
    prefix="/api/manager/mail",
    tags=["manager/mail"],
    dependencies=[Depends(get_current_username)],
)


def _email_lead_import_response(result) -> EmailLeadImportResponse | None:
    if not result:
        return None
    payload = {
        **result.__dict__,
        "decisions": [EmailLeadDecisionResponse(**item.__dict__) for item in result.decisions],
    }
    return EmailLeadImportResponse(**payload)


def _email_lead_import_job_response(snapshot: EmailLeadImportJobSnapshot) -> EmailLeadImportJobResponse:
    return EmailLeadImportJobResponse(
        status=snapshot.status,
        source=snapshot.source,
        dry_run=snapshot.dry_run,
        lookback_days=snapshot.lookback_days,
        started_at=snapshot.started_at,
        finished_at=snapshot.finished_at,
        last_import_at=snapshot.last_import_at,
        notified_admins=snapshot.notified_admins,
        already_running=snapshot.already_running,
        error=snapshot.error,
        message=snapshot.message,
        result=_email_lead_import_response(snapshot.result),
    )


@router.post(
    "/bank-receipts/import",
    response_model=BankReceiptImportResponse,
    operation_id=IMPORT_MANAGER_BANK_RECEIPTS,
)
async def import_manager_bank_receipts(
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await MailImapService.import_bank_receipts(session, limit=limit)
        return BankReceiptImportResponse(**result.__dict__)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=IMPORT_MANAGER_BANK_RECEIPTS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/leads/import",
    response_model=EmailLeadImportJobResponse,
    operation_id=IMPORT_MANAGER_EMAIL_LEADS,
)
async def import_manager_email_leads(
    dry_run: bool = Query(False),
    lookback_days: int | None = Query(None, ge=1, le=30),
):
    try:
        snapshot = await EmailLeadImportJobService.start_manual_import(
            dry_run=dry_run,
            lookback_days=lookback_days,
        )
        return _email_lead_import_job_response(snapshot)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=IMPORT_MANAGER_EMAIL_LEADS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.get(
    "/leads/import/status",
    response_model=EmailLeadImportJobResponse,
    operation_id=GET_MANAGER_EMAIL_LEAD_IMPORT_STATUS,
)
async def get_manager_email_lead_import_status():
    snapshot = await EmailLeadImportJobService.get_status()
    return _email_lead_import_job_response(snapshot)


@router.post(
    "/bank-receipts/import-statement",
    response_model=BankStatementImportResponse,
    operation_id=IMPORT_MANAGER_BANK_STATEMENT,
)
async def import_manager_bank_statement(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    try:
        content = await file.read()
        result = await BankStatementCsvService.import_statement(session, content)
        return BankStatementImportResponse(**result.__dict__)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=IMPORT_MANAGER_BANK_STATEMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.get(
    "/bank-receipts",
    response_model=BankReceiptListResponse,
    operation_id=LIST_MANAGER_BANK_RECEIPTS,
)
async def list_manager_bank_receipts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: str | None = None,
    payer_unp: str | None = None,
    order_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    items, total = await BankReceiptService.list_receipts(
        session,
        page=page,
        limit=limit,
        status=status,
        payer_unp=payer_unp,
        order_id=order_id,
    )
    return BankReceiptListResponse(items=items, total=total, page=page, limit=limit)


@router.post(
    "/bank-receipts/{receipt_id}/attach",
    response_model=BankReceiptResponse,
    operation_id=ATTACH_MANAGER_BANK_RECEIPT,
)
async def attach_manager_bank_receipt(
    receipt_id: int,
    payload: BankReceiptAttachPayload,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await BankReceiptService.attach_receipt_to_order(
            session,
            receipt_id=receipt_id,
            order_id=payload.order_id,
            payment_type=payload.payment_type,
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=ATTACH_MANAGER_BANK_RECEIPT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/bank-receipts/{receipt_id}/attach-group",
    response_model=BankReceiptResponse,
    operation_id=ATTACH_MANAGER_BANK_RECEIPT_GROUP,
)
async def attach_manager_bank_receipt_group(
    receipt_id: int,
    payload: BankReceiptGroupAttachPayload,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await BankReceiptService.attach_receipt_to_order_group(
            session,
            receipt_id=receipt_id,
            order_ids=payload.order_ids,
            payment_type=payload.payment_type,
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=ATTACH_MANAGER_BANK_RECEIPT_GROUP,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.patch(
    "/bank-receipts/{receipt_id}/status",
    response_model=BankReceiptResponse,
    operation_id=PATCH_MANAGER_BANK_RECEIPT_STATUS,
)
async def patch_manager_bank_receipt_status(
    receipt_id: int,
    payload: BankReceiptStatusPayload,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await BankReceiptService.update_receipt_status(
            session,
            receipt_id=receipt_id,
            status=payload.status,
            reason=payload.reason,
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_BANK_RECEIPT_STATUS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.delete(
    "/bank-receipts/{receipt_id}",
    response_model=dict,
    operation_id=DELETE_MANAGER_BANK_RECEIPT,
)
async def delete_manager_bank_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
):
    try:
        await BankReceiptService.delete_receipt(session, receipt_id=receipt_id)
        return {"ok": True}
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=DELETE_MANAGER_BANK_RECEIPT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/email/send-test",
    response_model=OutgoingEmailResponse,
    operation_id=SEND_MANAGER_TEST_EMAIL,
)
async def send_manager_test_email(
    payload: OutgoingEmailSendPayload,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await MailSmtpService.send_and_record(
            session,
            to_email=payload.to_email,
            subject=payload.subject,
            body_text=payload.body_text,
            body_html=payload.body_html,
            reply_to=payload.reply_to,
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=SEND_MANAGER_TEST_EMAIL,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/orders/{order_id}/email",
    response_model=OutgoingEmailResponse,
    operation_id=SEND_MANAGER_ORDER_EMAIL,
)
async def send_manager_order_email(
    order_id: int,
    payload: OrderEmailSendPayload,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await MailSmtpService.send_order_email(
            session,
            order_id=order_id,
            to_email=payload.to_email,
            subject=payload.subject,
            body_text=payload.body_text,
            body_html=payload.body_html,
            reply_to=payload.reply_to,
            document_ids=payload.document_ids,
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=SEND_MANAGER_ORDER_EMAIL,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
