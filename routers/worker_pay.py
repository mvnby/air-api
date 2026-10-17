"""Scoped worker remuneration commands and private, safe personal history."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.worker_money import WorkerMoneyCommandResult, WorkerMoneyCorrection
from api_contracts.worker_pay import (
    ManagerWorkerPayWorkspace,
    WorkerPayAgreementAction,
    WorkerPayAgreementCancel,
    WorkerPayAgreementCreate,
    WorkerPayAgreementRevise,
    WorkerPayOffsetCreate,
    WorkerPayOrderWorkspace,
    WorkerPayOverview,
    WorkerPayPayoutCreate,
    WorkerPayWorkspace,
)
from core.database import get_session
from core.security import (
    AuthenticatedUser,
    get_current_installer_context,
    require_manager_access,
)
from routers.installer_workspace import installer_errors
from routers.manager_operation_ids import (
    LIST_MANAGER_WORKER_PAY,
    GET_MANAGER_WORKER_PAY,
    GET_MANAGER_ORDER_WORKER_PAY,
    CREATE_MANAGER_WORKER_PAY_AGREEMENT,
    REVISE_MANAGER_WORKER_PAY_AGREEMENT,
    ACCRUE_MANAGER_WORKER_PAY_AGREEMENT,
    CANCEL_MANAGER_WORKER_PAY_AGREEMENT,
    CREATE_MANAGER_WORKER_PAY_PAYOUT,
    CREATE_MANAGER_WORKER_PAY_OFFSET,
    REVERSE_MANAGER_WORKER_PAY_PAYOUT,
)
from routers.manager_staff_invitations import require_team_origin
from services.command_transaction import command_transaction
from services.worker_pay_service import WorkerPayService as Pay

installer_router = APIRouter(prefix="/api/installer", tags=["installer-pay"])
manager_router = APIRouter(prefix="/api/manager", tags=["manager-worker-pay"])
protected = [Depends(require_team_origin)]


@installer_router.get(
    "/pay", response_model=WorkerPayWorkspace, operation_id="get_installer_pay"
)
async def own_pay(
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Read only personal pay history without order costs, other staff pay or private notes.

    Live identity and actual company membership are required; work closure/revocation
    does not erase liabilities. Pagination is bounded, reads create no account.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await Pay.workspace(session, auth, page=page, limit=limit)


@manager_router.get(
    "/worker-pay",
    response_model=WorkerPayOverview,
    operation_id=LIST_MANAGER_WORKER_PAY,
)
async def overview(
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Read scoped worker obligations with live pay authority or verified support access.

    Former worker liabilities remain visible. Pay and cash authorities are separate;
    offset needs both. A finance grant does not grant access to order commercial data.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await Pay.overview(session, auth, page, limit)


@manager_router.get(
    "/worker-pay/{worker_profile_id}",
    response_model=ManagerWorkerPayWorkspace,
    operation_id=GET_MANAGER_WORKER_PAY,
)
async def worker_pay(
    worker_profile_id: int,
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Read one scoped worker's frozen agreements, obligations and settlement history.

    A foreign profile is404. Safe own projection omits BYN expense equivalents;
    this Manager projection exposes reviewed frozen costs. No-store, bounded pagination.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await Pay.workspace(
            session,
            auth,
            profile_id=worker_profile_id,
            manager=True,
            page=page,
            limit=limit,
        )


@manager_router.get(
    "/orders/{order_id}/worker-pay",
    response_model=WorkerPayOrderWorkspace,
    operation_id=GET_MANAGER_ORDER_WORKER_PAY,
)
async def order_pay(
    order_id: int,
    response: Response,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Read eligible explicit assigned works and existing immutable order pay agreements.

    Requires live pay authority plus scoped CRM access. Candidate reads never create
    accounts; version0 is returned before first command. Foreign orders return404.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await Pay.order_workspace(session, auth, order_id)


@manager_router.post(
    "/orders/{order_id}/worker-pay/agreements",
    response_model=WorkerMoneyCommandResult,
    operation_id=CREATE_MANAGER_WORKER_PAY_AGREEMENT,
    dependencies=protected,
)
async def agree(
    order_id: int,
    payload: WorkerPayAgreementCreate,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Agree fixed positive pay for a live assigned work, freezing its reviewed BYN cost.

    Live pay authority, Origin/header, shared account version and UUID key are required.
    Foreign pay needs explicit BYN cost; BYN cost equals amount. Cost enters the order
    once at agreement, active work cannot be duplicated and legacy positive pay conflicts.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Pay.create_agreement(session, auth, order_id, payload)


@manager_router.post(
    "/worker-pay/{worker_profile_id}/agreements/{agreement_id}/revise",
    response_model=WorkerMoneyCommandResult,
    operation_id=REVISE_MANAGER_WORKER_PAY_AGREEMENT,
    dependencies=protected,
)
async def revise(
    worker_profile_id: int,
    agreement_id: int,
    payload: WorkerPayAgreementRevise,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Revise agreed, unaccrued pay with fresh account/agreement versions and frozen cost.

    Requires live pay management, Origin/header and durable UUID. Accrued/cancelled
    rows cannot be edited. Updates the order cost atomically without creating Payment.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Pay.change_agreement(
                session, auth, worker_profile_id, agreement_id, payload, action="revise"
            )


@manager_router.post(
    "/worker-pay/{worker_profile_id}/agreements/{agreement_id}/accrue",
    response_model=WorkerMoneyCommandResult,
    operation_id=ACCRUE_MANAGER_WORKER_PAY_AGREEMENT,
    dependencies=protected,
)
async def accrue(
    worker_profile_id: int,
    agreement_id: int,
    payload: WorkerPayAgreementAction,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Accrue agreed pay into a payable liability without charging order cost again.

    Live pay management, Origin/header, account/agreement versions and UUID required.
    Completed/revoked work retains its valid agreement; history stays independent of ACL.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Pay.change_agreement(
                session, auth, worker_profile_id, agreement_id, payload, action="accrue"
            )


@manager_router.post(
    "/worker-pay/{worker_profile_id}/agreements/{agreement_id}/cancel",
    response_model=WorkerMoneyCommandResult,
    operation_id=CANCEL_MANAGER_WORKER_PAY_AGREEMENT,
    dependencies=protected,
)
async def cancel(
    worker_profile_id: int,
    agreement_id: int,
    payload: WorkerPayAgreementCancel,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Cancel only entirely unpaid pay with a reason and preserve the original agreement.

    Requires fresh pay authority, Origin/header and both versions/UUID. Existing payouts
    must first be reversed. Cost removal and cancellation are atomic; no history deleted.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Pay.change_agreement(
                session, auth, worker_profile_id, agreement_id, payload, action="cancel"
            )


@manager_router.post(
    "/worker-pay/{worker_profile_id}/payouts",
    response_model=WorkerMoneyCommandResult,
    operation_id=CREATE_MANAGER_WORKER_PAY_PAYOUT,
    dependencies=protected,
)
async def payout(
    worker_profile_id: int,
    payload: WorkerPayPayoutCreate,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Record an external cash/bank remuneration payout allocated FIFO to accrued same-currency pay.

    Requires live pay authority, Origin/header, account version and UUID. No advances or
    overpayment; custody of customer money and customer Payments remain independent.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Pay.create_payout(session, auth, worker_profile_id, payload)


@manager_router.post(
    "/worker-pay/{worker_profile_id}/offsets",
    response_model=WorkerMoneyCommandResult,
    operation_id=CREATE_MANAGER_WORKER_PAY_OFFSET,
    dependencies=protected,
)
async def offset(
    worker_profile_id: int,
    payload: WorkerPayOffsetCreate,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Explicitly offset accrued unpaid remuneration against free customer cash in the same currency.

    Requires both live pay/cash grants, Origin/header, shared account version and UUID.
    Pending reservations and other currencies cannot fund an offset. Both FIFO allocations
    and balances change atomically; no client Payment or second order cost is created.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Pay.create_payout(
                session, auth, worker_profile_id, payload, offset=True
            )


@manager_router.post(
    "/worker-pay/{worker_profile_id}/payouts/{payout_id}/reverse",
    response_model=WorkerMoneyCommandResult,
    operation_id=REVERSE_MANAGER_WORKER_PAY_PAYOUT,
    dependencies=protected,
)
async def reverse(
    worker_profile_id: int,
    payout_id: int,
    payload: WorkerMoneyCorrection,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Reverse a payout or offset with a reason, restoring the original obligations.

    Requires fresh pay authority, account version, Origin/header and UUID; offset reversal
    additionally needs cash authority and restores custody. Original rows/allocations stay
    immutable, customer Payments and frozen order cost are unchanged. Identical replay safe.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            return await Pay.reverse_payout(
                session, auth, worker_profile_id, payout_id, payload
            )
