from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import (
    COMPOSE_MANAGER_NATIVE_ORDER_EMAIL,
    SEND_MANAGER_NATIVE_ORDER_EMAIL,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    OrderEmailComposePayload,
    OrderEmailComposeResponse,
    OrderEmailSendPayload,
    OutgoingEmailResponse,
)
from services.mail_smtp_service import (
    MailSmtpService,
    PartnerTenantSmtpUnavailableError,
)
from services.order_email_template_service import OrderEmailTemplateService


router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.post(
    "/orders/{order_id}/email/compose",
    response_model=OrderEmailComposeResponse,
    operation_id=COMPOSE_MANAGER_NATIVE_ORDER_EMAIL,
)
async def compose_native_order_email(
    order_id: int,
    payload: OrderEmailComposePayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> OrderEmailComposeResponse:
    """
    Compose suggested recipient, subject/body and selected document attachments for an
    accessible order in the current tenant/storefront. Preview only: does not submit email
    or mark documents sent. Invalid document/template/order selection returns 400.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OrderEmailTemplateService.compose(
            session,
            tenant_scope=auth.tenant_scope(),
            order_id=order_id,
            document_ids=payload.document_ids,
            template_key=payload.template_key,
        )
    except ValueError as exc:
        raise _email_error(
            400,
            COMPOSE_MANAGER_NATIVE_ORDER_EMAIL,
            "native_document_email_compose_invalid",
            exc,
        ) from exc


@router.post(
    "/orders/{order_id}/email",
    response_model=OutgoingEmailResponse,
    operation_id=SEND_MANAGER_NATIVE_ORDER_EMAIL,
)
async def send_native_order_email(
    order_id: int,
    payload: OrderEmailSendPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> OutgoingEmailResponse:
    """
    Send an email for an accessible order with selected native/legacy document attachments,
    recording outgoing-email state and document delivery. Manager access is required;
    current SMTP sending supports the system tenant only (409
    tenant_email_sender_not_configured for partner tenants). Invalid selection/content
    returns 400 and send failure 502. No caller idempotency receipt is provided: inspect
    outgoing-email history before repeating a lost send response. See the [document
    lifecycle
    contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    if not auth.is_system_tenant:
        raise manager_http_error(
            status_code=409,
            endpoint=SEND_MANAGER_NATIVE_ORDER_EMAIL,
            error_code="tenant_email_sender_not_configured",
            message=(
                "Отправка через почту «Мастер Воздуха» недоступна партнерскому "
                "аккаунту. Сначала подключите почту своей организации."
            ),
        )
    try:
        return await MailSmtpService.send_order_email(
            session,
            tenant_scope=auth.tenant_scope(),
            order_id=order_id,
            to_email=payload.to_email,
            subject=payload.subject,
            body_text=payload.body_text,
            body_html=payload.body_html,
            reply_to=payload.reply_to,
            document_ids=payload.document_ids,
        )
    except PartnerTenantSmtpUnavailableError as exc:
        raise _email_error(
            409,
            SEND_MANAGER_NATIVE_ORDER_EMAIL,
            "tenant_email_sender_not_configured",
            exc,
        ) from exc
    except ValueError as exc:
        raise _email_error(
            400,
            SEND_MANAGER_NATIVE_ORDER_EMAIL,
            "native_document_email_send_invalid",
            exc,
        ) from exc
    except RuntimeError as exc:
        raise _email_error(
            502,
            SEND_MANAGER_NATIVE_ORDER_EMAIL,
            "native_document_email_send_failed",
            RuntimeError("Не удалось отправить письмо. Проверьте настройки почты"),
        ) from exc


def _email_error(status_code: int, endpoint: str, code: str, exc: Exception):
    return manager_http_error(
        status_code=status_code,
        endpoint=endpoint,
        error_code=code,
        message=str(exc),
    )
