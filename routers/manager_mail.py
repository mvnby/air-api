import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST
from core.security import (
    get_current_manager_tenant_scope,
    require_system_manager_tenant_scope,
)
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    ATTACH_MANAGER_BANK_RECEIPT,
    ATTACH_MANAGER_BANK_RECEIPT_GROUP,
    COMPOSE_MANAGER_ORDER_EMAIL,
    DELETE_MANAGER_BANK_RECEIPT,
    GET_MANAGER_BANK_RECEIPT_ALLOCATION,
    IMPORT_MANAGER_BANK_RECEIPTS,
    IMPORT_MANAGER_BANK_STATEMENT,
    IMPORT_MANAGER_EMAIL_LEADS,
    GET_MANAGER_EMAIL_LEAD_IMPORT_STATUS,
    GET_MANAGER_OUTGOING_EMAIL,
    LIST_MANAGER_BANK_RECEIPTS,
    LIST_MANAGER_ORDER_OUTGOING_EMAILS,
    LIST_MANAGER_OUTGOING_EMAILS,
    PATCH_MANAGER_BANK_RECEIPT_STATUS,
    REPLACE_MANAGER_BANK_RECEIPT_ALLOCATIONS,
    RETRY_MANAGER_OUTGOING_EMAIL,
    SEND_MANAGER_ORDER_EMAIL,
    SEND_MANAGER_TEST_EMAIL,
)
from schemas import (
    BankReceiptAttachPayload,
    BankReceiptAllocationDetailResponse,
    BankReceiptAllocationsReplacePayload,
    BankReceiptGroupAttachPayload,
    BankReceiptImportResponse,
    BankReceiptListResponse,
    BankReceiptResponse,
    BankReceiptStatusPayload,
    BankStatementImportResponse,
    EmailLeadDecisionResponse,
    EmailLeadImportJobResponse,
    EmailLeadImportResponse,
    OrderEmailComposePayload,
    OrderEmailComposeResponse,
    OrderEmailSendPayload,
    OutgoingEmailDetailResponse,
    OutgoingEmailListResponse,
    OutgoingEmailResponse,
    OutgoingEmailSendPayload,
)
from services.bank_receipt_allocation_service import BankReceiptAllocationService
from services.bank_receipt_service import BankReceiptService
from services.bank_statement_csv_service import BankStatementCsvService
from services.email_lead_import_job_service import EmailLeadImportJobService, EmailLeadImportJobSnapshot
from services.mail_imap_service import MailImapService
from services.mail_smtp_service import MailSmtpService
from services.notification_service import NotificationService
from services.order_email_template_service import OrderEmailTemplateService
from services.outgoing_email_service import OutgoingEmailService


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/manager/mail",
    tags=["manager/mail"],
    dependencies=[Depends(require_system_manager_tenant_scope)],
)


async def _bank_receipt_response(
    session: AsyncSession,
    receipt,
    totals: dict[int, dict[str, float | int]] | None = None,
) -> BankReceiptResponse:
    receipt_id = int(receipt.id)
    allocation_totals = (
        totals
        if totals is not None
        else await BankReceiptAllocationService.get_totals(session, [receipt_id])
    )
    allocated_amount = float(allocation_totals.get(receipt_id, {}).get("allocated_amount") or 0)
    return BankReceiptResponse.model_validate(receipt).model_copy(
        update={
            "allocated_amount": allocated_amount,
            "unallocated_amount": max(0.0, round(float(receipt.amount or 0) - allocated_amount, 2)),
            "allocation_count": int(allocation_totals.get(receipt_id, {}).get("allocation_count") or 0),
        }
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Synchronously import up to 100 bank-notification messages from the configured IMAP
    source, deduplicate known receipts and run matching that can create linked order
    payments. New receipt notifications are attempted separately; notification failure does
    not undo import. Configured processed-folder handling can move successfully imported
    messages out of the source mailbox; invalid configuration/input returns 400. No caller
    replay receipt is supplied; inspect import counters/current receipts after uncertain
    results. Requires system-tenant Manager access. These are platform mail/receipt records,
    not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        result = await MailImapService.import_bank_receipts(session, limit=limit)
        if result.created_receipt_ids:
            try:
                await NotificationService.notify_admins_bank_receipts_imported(
                    session,
                    result.created_receipt_ids,
                    tenant_scope=tenant_scope,
                )
            except Exception:
                logger.exception(
                    "MANUAL_BANK_RECEIPT_NOTIFY_FAILED receipt_ids=%s",
                    result.created_receipt_ids,
                )
        return BankReceiptImportResponse(**result.__dict__)
    except ValueError as exc:
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
    """
    Start the shared process-local email-lead import in the background for the resolved
    system tenant/storefront. Requires system-tenant Manager access. Returns job state
    rather than completed counts; poll import/status. dry_run evaluates decisions without
    creating leads; lookback_days is 1–30 when supplied. A running import returns
    already_running rather than another concurrent task in this process; setup failure
    returns 400. This is not a durable or actor-specific job receipt.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Read the latest shared process-local manual/scheduled email-lead import snapshot.
    Requires system-tenant Manager access. idle/running/completed/failed and optional
    result/error describe the worker seen by this process; restart or another process can
    show a different snapshot. This read does not start or repeat an import.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Import a supported bank CSV statement into platform receipts, match existing credits
    using reconciliation keys and mark duplicate/missing-in-period candidates for review.
    New matches can create order payments. Parsing/provider/service failures return 400.
    Reads the uploaded file without a route-specific size cap; no caller idempotency receipt
    is supplied, and repeat imports can update reconciliation flags. Requires system-tenant
    Manager access. These are platform mail/receipt records, not a current-storefront-only
    journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Page platform bank receipts with optional status/payer/order filters and
    allocated/unallocated totals, newest first. limit is at most 100. Reading does not
    allocate funds or mark a receipt resolved. Requires system-tenant Manager access. These
    are platform mail/receipt records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    items, total = await BankReceiptService.list_receipts(
        session,
        page=page,
        limit=limit,
        status=status,
        payer_unp=payer_unp,
        order_id=order_id,
    )
    totals = await BankReceiptAllocationService.get_totals(
        session,
        [int(item.id) for item in items if item.id],
    )
    return BankReceiptListResponse(
        items=[await _bank_receipt_response(session, item, totals) for item in items],
        total=total,
        page=page,
        limit=limit,
    )


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
    """
    Allocate an unattached platform receipt to one selected open order up to its outstanding
    debt, create a payment and refresh finances; excess remains unallocated. This explicit
    manual action allows payer-UNP mismatch and records that override. Missing/already
    attached/invalid receipt or closed/missing/unpaid-balance-free order returns 400.
    Repeated attach is rejected, not receipt replay. Requires system-tenant Manager access.
    These are platform mail/receipt records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        receipt = await BankReceiptService.attach_receipt_to_order(
            session,
            receipt_id=receipt_id,
            order_id=payload.order_id,
            payment_type=payload.payment_type,
        )
        return await _bank_receipt_response(session, receipt)
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
    """
    Allocate an unattached platform receipt across at least two open orders with outstanding
    balances and the same payer UNP. Uses supplied IDs or the saved group suggestion; total
    group debt must match receipt amount within service money tolerance. Creates linked
    payments and refreshes all finances. Missing/invalid/already attached/mismatched context
    returns 400; repeated attach is not replayed. Requires system-tenant Manager access.
    These are platform mail/receipt records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        receipt = await BankReceiptService.attach_receipt_to_order_group(
            session,
            receipt_id=receipt_id,
            order_ids=payload.order_ids,
            payment_type=payload.payment_type,
        )
        return await _bank_receipt_response(session, receipt)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=ATTACH_MANAGER_BANK_RECEIPT_GROUP,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.get(
    "/bank-receipts/{receipt_id}/allocation",
    response_model=BankReceiptAllocationDetailResponse,
    operation_id=GET_MANAGER_BANK_RECEIPT_ALLOCATION,
)
async def get_manager_bank_receipt_allocation(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Read a platform receipt’s current allocations and candidate-order balances for review.
    Existing linked closed orders can appear; other candidates must be open and match payer
    UNP. Missing receipt or service failure returns 400. Does not replace payments or
    reserve allocation amounts. Requires system-tenant Manager access. These are platform
    mail/receipt records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await BankReceiptAllocationService.get_detail(
            session,
            receipt_id=receipt_id,
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=GET_MANAGER_BANK_RECEIPT_ALLOCATION,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.put(
    "/bank-receipts/{receipt_id}/allocations",
    response_model=BankReceiptResponse,
    operation_id=REPLACE_MANAGER_BANK_RECEIPT_ALLOCATIONS,
)
async def replace_manager_bank_receipt_allocations(
    receipt_id: int,
    payload: BankReceiptAllocationsReplacePayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Replace all platform payments allocated from this receipt with the supplied set and
    refresh every affected order. Requires distinct orders, positive amounts, matching payer
    UNP and amounts within receipt/debt; newly added closed orders are refused, existing
    linked closed orders remain eligible. Empty set clears allocations and returns
    requires_review. Identical normalized allocation/type state is a no-op; no caller key or
    expected_version precondition is supplied. Missing/invalid/ineligible context returns
    400. Requires system-tenant Manager access. These are platform mail/receipt records, not
    a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        receipt = await BankReceiptAllocationService.replace(
            session,
            receipt_id=receipt_id,
            allocations=[item.model_dump() for item in payload.allocations],
            payment_type=payload.payment_type,
        )
        return await _bank_receipt_response(session, receipt)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=REPLACE_MANAGER_BANK_RECEIPT_ALLOCATIONS,
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
    """
    Set a supported review/resolution status and manual reason on a platform receipt.
    matched/partially_allocated must be produced by allocation commands (400 otherwise).
    Moving to void/requires_review/closed_orders/non_order_income removes linked payments
    and refreshes all affected orders; this is not just a label edit.
    Missing/unsupported/service failure returns 400. No replay receipt or version
    precondition is supplied. Requires system-tenant Manager access. These are platform
    mail/receipt records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        receipt = await BankReceiptService.update_receipt_status(
            session,
            receipt_id=receipt_id,
            status=payload.status,
            reason=payload.reason,
        )
        return await _bank_receipt_response(session, receipt)
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
    """
    Delete a platform receipt only when it has no matched_payment_id. A receipt linked to
    payment must instead be marked erroneous through status handling. Missing receipt or
    refusal returns 400, including repeat after deletion. This does not delete the original
    mailbox message. Requires system-tenant Manager access. These are platform mail/receipt
    records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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


@router.get(
    "/outgoing-emails",
    response_model=OutgoingEmailListResponse,
    operation_id=LIST_MANAGER_OUTGOING_EMAILS,
)
async def list_manager_outgoing_emails(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: str | None = None,
    order_id: int | None = None,
    customer_id: int | None = None,
    recipient: str | None = None,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Page the platform outgoing-email journal with status/order/customer/recipient/text/date
    filters and limit at most 100. Includes attempts and delivery/error metadata;
    unsupported status or service failure returns 400. Reading does not send or retry
    messages. Requires system-tenant Manager access. These are platform mail/receipt
    records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        items, total = await OutgoingEmailService.list_emails(
            session,
            page=page,
            limit=limit,
            status=status,
            order_id=order_id,
            customer_id=customer_id,
            recipient=recipient,
            q=q,
            date_from=date_from,
            date_to=date_to,
        )
        return OutgoingEmailListResponse(items=items, total=total, page=page, limit=limit)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=LIST_MANAGER_OUTGOING_EMAILS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.get(
    "/outgoing-emails/{email_id}",
    response_model=OutgoingEmailDetailResponse,
    operation_id=GET_MANAGER_OUTGOING_EMAIL,
)
async def get_manager_outgoing_email(
    email_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Read a platform outgoing-email record including stored content/attachment metadata and
    its retry attempts. Missing record or any detail-loading failure is mapped to 404 by
    this route. Reading is not a delivery confirmation from the recipient’s mailbox and does
    not retry. Requires system-tenant Manager access. These are platform mail/receipt
    records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OutgoingEmailService.get_email_detail(session, email_id)
    except Exception as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_OUTGOING_EMAIL,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.get(
    "/orders/{order_id}/outgoing-emails",
    response_model=OutgoingEmailListResponse,
    operation_id=LIST_MANAGER_ORDER_OUTGOING_EMAILS,
)
async def list_manager_order_outgoing_emails(
    order_id: int,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """
    Read the first page of platform outgoing-email history filtered by order ID, with limit
    at most 100. This journal lookup does not perform the tenant/storefront order
    authorization used by compose/send. Service failure returns 400; an order without
    records can return an empty list. Requires system-tenant Manager access. These are
    platform mail/receipt records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        items, total = await OutgoingEmailService.list_emails(session, page=1, limit=limit, order_id=order_id)
        return OutgoingEmailListResponse(items=items, total=total, page=1, limit=limit)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=LIST_MANAGER_ORDER_OUTGOING_EMAILS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/outgoing-emails/{email_id}/retry",
    response_model=OutgoingEmailResponse,
    operation_id=RETRY_MANAGER_OUTGOING_EMAIL,
)
async def retry_manager_outgoing_email(
    email_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new linked attempt for a failed platform outgoing email using its stored
    recipient/body; only failed originals are accepted (400 otherwise). Messages with
    attachments cannot be reconstructed by this action: a failed attempt is recorded and
    documents must be sent again from the order. SMTP failure can return HTTP success with
    status=failed; inspect status/error. No caller replay receipt prevents another attempt.
    Requires system-tenant Manager access. These are platform mail/receipt records, not a
    current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OutgoingEmailService.retry_failed_email(session, email_id)
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=RETRY_MANAGER_OUTGOING_EMAIL,
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
    """
    Send a real message through the configured system SMTP and record the attempt in the
    platform journal. This is not a dry run despite the test route name. Invalid
    configuration/content or SMTP failure returns 400; a failed recorded attempt may already
    exist. No replay receipt is supplied, so inspect the journal before retrying an
    uncertain result. Requires system-tenant Manager access. These are platform mail/receipt
    records, not a current-storefront-only journal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    "/orders/{order_id}/compose",
    response_model=OrderEmailComposeResponse,
    operation_id=COMPOSE_MANAGER_ORDER_EMAIL,
)
async def compose_manager_order_email(
    order_id: int,
    payload: OrderEmailComposePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Preview suggested recipient/subject/body/attachments for an order accessible in the
    current system tenant/storefront. Requires system-tenant Manager access through the mail
    router. Does not send email or change proposal/document lifecycle; invalid
    order/document/template context returns 400.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OrderEmailTemplateService.compose(
            session,
            tenant_scope=tenant_scope,
            order_id=order_id,
            document_ids=payload.document_ids,
            registration_certificate_id=payload.registration_certificate_id,
            legal_entity_id=payload.legal_entity_id,
            template_key=payload.template_key,
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=COMPOSE_MANAGER_ORDER_EMAIL,
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Send email with selected documents from an order accessible in the current system
    tenant/storefront and record outgoing history. Requires system-tenant Manager access. At
    most 10 documents, 10 MB per PDF and 20 MB total; native documents must be issued.
    Success can mark native documents/proposals sent and advance negotiation substatus for
    offer/invoice/contract. Invalid context/content or SMTP failure returns 400. No caller
    replay receipt is supplied: inspect history before repeating an uncertain send.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await MailSmtpService.send_order_email(
            session,
            tenant_scope=tenant_scope,
            order_id=order_id,
            to_email=payload.to_email,
            subject=payload.subject,
            body_text=payload.body_text,
            body_html=payload.body_html,
            reply_to=payload.reply_to,
            document_ids=payload.document_ids,
            registration_certificate_id=payload.registration_certificate_id,
            legal_entity_id=payload.legal_entity_id,
        )
    except Exception as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=SEND_MANAGER_ORDER_EMAIL,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
