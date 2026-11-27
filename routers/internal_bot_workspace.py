"""Private manager CRM for the Telegram Mini App."""

from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import BotQuickOrderDraftSessionResponse
from api_contracts.bot_workspace import (
    BotWorkspaceActor, BotWorkspaceDetail, BotWorkspaceList, BotWorkspaceOrderResult, BotWorkspaceReadRequest,
    BotWorkspaceServiceOrderRequest, BotWorkspaceTaskRequest, IncomingKind, WorkspaceSection,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_business_context import bind_bot_business_context
from services.bot_workspace_order_service import customer_draft, service_order_from_incoming
from services.bot_workspace_service import change_task_status, list_workspace, set_incoming_read, workspace_detail, workspace_for
from services.lead_service import LeadVersionConflict
from services.leads_inbox_service import InboxError
from services.order_responsibility_service import OrderResponsibilityError
from services.personal_task_service import PersonalTaskStatusConflictError, PersonalTaskVersionConflictError
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable


router = APIRouter(
    prefix="/api/internal/bot/v1/workspace", tags=["internal bot v1"],
    dependencies=[Depends(require_bot_api_token), Depends(bind_bot_business_context, scope="function")],
)
ItemId = Annotated[int, Path(gt=0, le=2**31-1)]
Session = Annotated[AsyncSession, Depends(get_session)]


@contextmanager
def workspace_errors():
    try:
        yield
    except (InboxError, OrderResponsibilityError) as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except (PersonalTaskVersionConflictError, PersonalTaskStatusConflictError, PublicWriteIdempotencyConflict,
            LeadVersionConflict) as exc:
        raise HTTPException(409, str(exc)) from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(503, "Повторите команду", headers={"Retry-After": "1"}) from exc
    except LookupError as exc:
        raise HTTPException(404, "Запись недоступна") from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{section}", response_model=BotWorkspaceList, operation_id="list_internal_bot_workspace_v1")
async def list_section(section: WorkspaceSection, session: Session, telegram_id: int = Query(gt=0),
                       expected_context_version: int = Query(ge=0), q: str = Query("", max_length=160),
                       filter: str | None = Query(None, max_length=32), page: int = Query(1, ge=1, le=1000000),
                       limit: int = Query(20, ge=1, le=40)):
    """Search and page Manager inbox, orders, customers or personal tasks. The selected
    tenant/site and real staff actor fence rows and counts. Customers belong to the
    tenant, orders and inbox to the site, tasks to their author or assignee. Requires
    the bot service token, active manager (403) and current context version (409).
    Invalid section/filter returns 422. Reading the inbox does not mark it read."""
    with workspace_errors():
        ws = await workspace_for(session, telegram_id)
        return await list_workspace(session, ws, section, query=q.strip(), selected_filter=filter, page=page, limit=limit)


@router.get("/{section}/{item_id}", response_model=BotWorkspaceDetail, operation_id="get_internal_bot_workspace_item_v1")
async def get_item(section: WorkspaceSection, item_id: ItemId, session: Session, telegram_id: int = Query(gt=0),
                   expected_context_version: int = Query(ge=0), kind: IncomingKind | None = None):
    """Read one CRM card and its scoped Manager link. Inbox IDs require kind=lead|order.
    Requires the bot service token, active manager and current context revision.
    Inaccessible objects return 404, unauthorized actors 403 and stale company context 409."""
    with workspace_errors():
        return await workspace_detail(session, await workspace_for(session, telegram_id), section, item_id, kind)


@router.post("/tasks/{item_id}/status", response_model=BotWorkspaceDetail, operation_id="set_internal_bot_workspace_task_status_v1")
async def task_status(item_id: ItemId, payload: BotWorkspaceTaskRequest, session: Session):
    """Complete or reopen a visible personal task with its issued version and idempotency key.
    Requires service authentication and a writable current manager membership. Stale versions
    and conflicting keys return 409; inaccessible tasks return 404. A retry uses the same key."""
    with workspace_errors():
        return await change_task_status(session, await workspace_for(session, payload.telegram_id), item_id, payload)


@router.post("/incoming/{item_id}/read", response_model=BotWorkspaceDetail, operation_id="set_internal_bot_workspace_incoming_read_v1")
async def incoming_read(item_id: ItemId, payload: BotWorkspaceReadRequest, session: Session):
    """Set the current manager's personal read flag for one scoped Lead/Order inbox card.
    Repeating the same value preserves its read state. Service token and writable company
    version are required. Missing items return 404 and stale context returns 409."""
    with workspace_errors():
        return await set_incoming_read(session, await workspace_for(session, payload.telegram_id), item_id, payload)


@router.post("/customers/{item_id}/draft", response_model=BotQuickOrderDraftSessionResponse, operation_id="start_internal_bot_workspace_customer_draft_v1")
async def start_customer_draft(item_id: ItemId, payload: BotWorkspaceActor, session: Session):
    """Open a new quick-order draft prefilled from the active tenant customer. The draft
    belongs to this Telegram actor and company/site revision. Each call starts a draft.
    Requires the service token and a writable manager membership; inaccessible clients return 404."""
    with workspace_errors():
        ws = await workspace_for(session, payload.telegram_id)
        return await customer_draft(session, ws, item_id, payload.telegram_id)


@router.post("/incoming/{item_id}/service-order", response_model=BotWorkspaceOrderResult, operation_id="qualify_internal_bot_workspace_incoming_v1")
async def qualify_incoming(item_id: ItemId, payload: BotWorkspaceServiceOrderRequest, session: Session):
    """Create a negotiation-stage service order from the selected incoming and active
    customer, retaining the source link or promoting an Order intake in place. Requires
    a service token, writable manager, current company and source version, and a stable
    idempotency key on retry. Missing inputs return 404 and stale revisions return 409."""
    with workspace_errors():
        return await service_order_from_incoming(session, await workspace_for(session, payload.telegram_id), item_id, payload)
