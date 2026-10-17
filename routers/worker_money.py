"""Client-money confirmation and scoped worker cash custody commands."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.worker_money import (
    ClientMoneyReceived,
    WorkerCashHandoverAction,
    WorkerCashHandoverCreate,
    WorkerMoneyCommandResult,
    WorkerMoneyCorrection,
    WorkerMoneyOverview,
    WorkerMoneyRecipients,
    WorkerMoneyWorkspace,
)
from core.database import get_session
from core.security import (
    AuthenticatedUser,
    get_current_installer_context,
    require_manager_access,
)
from routers.installer_workspace import installer_errors
from routers.manager_operation_ids import (
    CONFIRM_MANAGER_CASH_HANDOVER,
    GET_MANAGER_WORKER_MONEY,
    LIST_MANAGER_WORKER_MONEY,
    REJECT_MANAGER_CASH_HANDOVER,
    REVERSE_MANAGER_WORKER_RECEIPT,
)
from routers.manager_staff_invitations import require_team_origin
from routers.manager_operation_ids import REVERSE_MANAGER_CASH_HANDOVER
from services.command_transaction import command_transaction
from services.worker_money_service import WorkerMoneyService as Money

installer_router = APIRouter(prefix="/api/installer", tags=["installer-money"])
manager_router = APIRouter(
    prefix="/api/manager/worker-money", tags=["manager-worker-money"]
)
protected = [Depends(require_team_origin)]


@installer_router.get(
    "/money", response_model=WorkerMoneyWorkspace, operation_id="get_installer_money"
)
async def own_money(
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Read only personal cash balances and paginated immutable receipt history in the selected company/site.

    Active real membership is required; support impersonation is forbidden. Closed or
    revoked work does not erase financial history or restore order access. No prices,
    purchases, supplier data or other workers' transactions are exposed. No-store.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await Money.workspace(session, auth, page=page, limit=limit)


@installer_router.get(
    "/money/recipients",
    response_model=WorkerMoneyRecipients,
    operation_id="list_installer_money_recipients",
)
async def recipients(
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """List other active actual company members authorized to acknowledge cash receipt.

    Returns only names/identifiers of owners, administrators and managers explicitly
    granted worker.money.manage. A platform support identity is never a recipient.
    Pagination is bounded at 100; this read creates no account or financial entry.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await Money.recipients(session, auth, page=page, limit=limit)


@installer_router.post(
    "/works/{assignment_id}/collections",
    response_model=WorkerMoneyCommandResult,
    operation_id="confirm_installer_client_money",
    dependencies=protected,
)
async def receive(
    assignment_id: int,
    payload: ClientMoneyReceived,
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Confirm actual full/partial client cash against a live reviewed collection instruction.

    Team Origin/header and current designated assignment are required. Exact positive
    amount/currency cannot exceed the instruction or fresh customer balance. Atomically
    records one Payment, cash custody, consumed instruction/version and audit. A UUID
    key replays the committed result; changed payload/key reuse or stale version is409.
    Foreign/revoked assignments are404. Receiving cash is not installer remuneration.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Money.receive(session, auth, assignment_id, payload)


@installer_router.post(
    "/money/handovers",
    response_model=WorkerMoneyCommandResult,
    operation_id="create_installer_cash_handover",
    dependencies=protected,
)
async def create_handover(
    payload: WorkerCashHandoverCreate,
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Report cash handed to an eligible company recipient, reserving personal available funds.

    Requires team Origin/header, fresh account version and UUID replay key. Exact
    currency-specific funds are allocated to source receipts and reserved atomically.
    Money remains held until the selected recipient acknowledges it. Overbooking,
    self-recipient or unavailable recipient is rejected; this never adds client Payment.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Money.create_handover(session, auth, payload)


@installer_router.post(
    "/money/handovers/{handover_id}/cancel",
    response_model=WorkerMoneyCommandResult,
    operation_id="cancel_installer_cash_handover",
    dependencies=protected,
)
async def cancel_handover(
    handover_id: int,
    payload: WorkerCashHandoverAction,
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Cancel only the actor's pending handover using its row version and a UUID key.

    Team Origin/header and live identity are required. Releases reservations without
    changing client payment or erasing history. Already resolved or stale requests
    return409; foreign company/site/account identifiers return404. Safe identical replay.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Money.resolve_handover(
                session, auth, handover_id, payload, action="cancel"
            )


@manager_router.get(
    "", response_model=WorkerMoneyOverview, operation_id=LIST_MANAGER_WORKER_MONEY
)
async def overview(
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Read company/site worker cash balances with bounded pagination and live CRM authority.

    Includes historical accounts of disabled workers so liabilities do not disappear.
    can_manage independently describes cash-command authority; CRM alone cannot
    acknowledge transfers or reverse receipts. Reads do not provision accounts.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await Money.overview(session, auth, page=page, limit=limit)


@manager_router.get(
    "/{worker_profile_id}",
    response_model=WorkerMoneyWorkspace,
    operation_id=GET_MANAGER_WORKER_MONEY,
)
async def worker_money(
    worker_profile_id: int,
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Read selected company/site worker cash history without granting access to other tenants.

    Requires fresh CRM authority; a foreign worker returns404. History survives work
    closure/revocation. Exact balances distinguish held, pending and available funds;
    can_reverse applies only to fully unallocated receipts. Responses are no-store.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await Money.workspace(
            session,
            auth,
            profile_id=worker_profile_id,
            manager=True,
            page=page,
            limit=limit,
        )


@manager_router.post(
    "/{worker_profile_id}/handovers/{handover_id}/confirm",
    response_model=WorkerMoneyCommandResult,
    operation_id=CONFIRM_MANAGER_CASH_HANDOVER,
    dependencies=protected,
)
async def confirm_handover(
    worker_profile_id: int,
    handover_id: int,
    payload: WorkerCashHandoverAction,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Acknowledge actual cash receipt as the selected recipient with live cash-management authority.

    Actual owner/admin or explicit worker.money.manage membership, team Origin/header,
    handover version and UUID key are required. Another recipient/support cannot confirm.
    Pending reservations become confirmed cash handed over atomically; no second client
    Payment is created. Conflicts are409; identical committed commands replay safely.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Money.resolve_handover(
                session,
                auth,
                handover_id,
                payload,
                profile_id=worker_profile_id,
                action="confirm",
            )


@manager_router.post(
    "/{worker_profile_id}/handovers/{handover_id}/reject",
    response_model=WorkerMoneyCommandResult,
    operation_id=REJECT_MANAGER_CASH_HANDOVER,
    dependencies=protected,
)
async def reject_handover(
    worker_profile_id: int,
    handover_id: int,
    payload: WorkerCashHandoverAction,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Reject a pending scoped handover with live owner/admin or delegated cash authority.

    Team Origin/header, current handover version and UUID key are required. Releases
    reserved cash, preserves the request/audit and changes no client payments. Foreign
    identifiers are404, stale/resolved operations409, identical replay is safe.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Money.resolve_handover(
                session,
                auth,
                handover_id,
                payload,
                profile_id=worker_profile_id,
                action="reject",
            )


@manager_router.post(
    "/{worker_profile_id}/receipts/{receipt_id}/reverse",
    response_model=WorkerMoneyCommandResult,
    operation_id=REVERSE_MANAGER_WORKER_RECEIPT,
    dependencies=protected,
)
async def reverse_receipt(
    worker_profile_id: int,
    receipt_id: int,
    payload: WorkerMoneyCorrection,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Correct an entirely unallocated erroneous receipt with an explicit reason and counter-payment.

    Live cash-management authority, team Origin/header, account version and UUID key
    are required. Original receipt/Payment remain immutable. Confirmed/pending handover
    funds cannot be reversed; cancel pending handovers first. The corrective negative
    Payment, audit and cash reversal are atomic; collection requires Manager review.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Money.reverse_receipt(
                session, auth, worker_profile_id, receipt_id, payload
            )


@manager_router.post(
    "/{worker_profile_id}/handovers/{handover_id}/reverse",
    response_model=WorkerMoneyCommandResult,
    operation_id=REVERSE_MANAGER_CASH_HANDOVER,
    dependencies=protected,
)
async def reverse_handover(
    worker_profile_id: int,
    handover_id: int,
    payload: WorkerMoneyCorrection,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Correct confirmed cash receipt with a reason while retaining original recipient and dates.

    Requires live cash-management authority, Origin/header, shared account version and
    durable UUID. Restores the worker's cash custody and releases source allocations;
    original amount, recipient and confirmation timestamp remain. No client Payment.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Money.reverse_handover(
                session, auth, worker_profile_id, handover_id, payload
            )
