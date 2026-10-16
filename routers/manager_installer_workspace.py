"""Manager control of explicit assignments, approved information and collection instructions."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.installer_workspace import (
    ManagerCollectionUpdate,
    ManagerInstallerWorkspace,
    WorkerAssignmentCreate,
    WorkerAssignmentPublicationUpdate,
    WorkerAssignmentRevoke,
    WorkerCandidatesResponse,
)
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers.installer_workspace import installer_errors
from routers.manager_staff_invitations import require_team_origin
from services.command_transaction import command_transaction
from services.installer_collection_service import InstallerCollectionService
from services.installer_workspace_service import InstallerWorkspaceService
from services.worker_assignment_service import WorkerAssignmentService

router = APIRouter(prefix="/api/manager", tags=["manager-installer-workspace"])
protected = [Depends(require_team_origin)]


@router.get(
    "/worker-candidates",
    response_model=WorkerCandidatesResponse,
    operation_id="list_manager_worker_candidates",
)
async def candidates(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=100),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Page active actual company owner/admin/manager/installer assignment candidates.

    Requires CRM access; virtual support is allowed to manage a partner, but does not
    become a candidate without actual membership. No credentials/payroll are returned.
    """
    async with installer_errors(session):
        return await WorkerAssignmentService.candidates(session, auth, page, limit)


@router.get(
    "/orders/{order_id}/installer-workspace",
    response_model=ManagerInstallerWorkspace,
    operation_id="get_manager_installer_workspace",
)
async def workspace(
    order_id: int,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Read scoped work grants, approved publications and the current collection review state.

    CRM membership or verified platform support is required. A foreign/missing order
    returns404. Financial balances/fingerprint are Manager-only and do not create or
    repair any proposal, assignment, payment or worker profile.
    """
    async with installer_errors(session):
        return await InstallerWorkspaceService.manager_view(session, auth, order_id)


@router.post(
    "/orders/{order_id}/installer-workspace/assignments",
    response_model=ManagerInstallerWorkspace,
    status_code=201,
    operation_id="create_manager_worker_assignment",
    dependencies=protected,
)
async def create_assignment(
    order_id: int,
    payload: WorkerAssignmentCreate,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Explicitly assign an actual company worker to an order or active visit.

    Requires X-Kitlane-Team:1 and approved Origin. Fresh authority/eligibility and scope
    are checked under ordered locks. Creates a company worker profile if needed;
    does not copy internal comments, grant CRM or create payroll/payment records.
    Assignment and audit commit atomically; duplicate active assignments are reused.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            await WorkerAssignmentService.create(session, auth, order_id, payload)
            result = await InstallerWorkspaceService.manager_view(
                session, auth, order_id
            )
        return result


@router.patch(
    "/orders/{order_id}/installer-workspace/assignments/{assignment_id}",
    response_model=ManagerInstallerWorkspace,
    operation_id="publish_manager_worker_assignment",
    dependencies=protected,
)
async def publish_assignment(
    order_id: int,
    assignment_id: int,
    payload: WorkerAssignmentPublicationUpdate,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Publish only explicitly approved work title/instructions and technical attachment links.

    Requires team Origin/header protection and fresh scoped CRM authority. A stale
    assignment version returns409; unavailable/nontechnical/foreign materials are
    rejected. Version, publications and audit are atomic, preserving unrelated order
    fields and financial data.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            await InstallerWorkspaceService.publish(
                session, auth, order_id, assignment_id, payload
            )
            result = await InstallerWorkspaceService.manager_view(
                session, auth, order_id
            )
        return result


@router.post(
    "/orders/{order_id}/installer-workspace/assignments/{assignment_id}/revoke",
    response_model=ManagerInstallerWorkspace,
    operation_id="revoke_manager_worker_assignment",
    dependencies=protected,
)
async def revoke_assignment(
    order_id: int,
    assignment_id: int,
    payload: WorkerAssignmentRevoke,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Revoke versioned work access with atomic audit; preserve payroll/history and files.

    Requires team Origin/header protection and fresh scoped CRM authority. Stale
    versions return409. New reads, downloads and old bot actions lose authorization;
    the original assignment identity is never reassigned to a different person.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            await WorkerAssignmentService.revoke(
                session, auth, order_id, assignment_id, payload.expected_version
            )
            result = await InstallerWorkspaceService.manager_view(
                session, auth, order_id
            )
        return result


@router.put(
    "/orders/{order_id}/installer-workspace/collection",
    response_model=ManagerInstallerWorkspace,
    operation_id="put_manager_worker_collection",
    dependencies=protected,
)
async def collection(
    order_id: int,
    payload: ManagerCollectionUpdate,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
):
    """Publish/clear one versioned collection instruction to one assigned recipient.

    Requires team Origin/header protection, live CRM authority, an unchanged financial
    fingerprint and exact nonnegative money no greater than the current balance in
    the supported currency. Zero is explicit; null clears. Stale edits return409.
    This is not confirmation of receipt and never inserts/changes payments or payroll.
    """
    async with installer_errors(session):
        async with command_transaction(session):
            await InstallerCollectionService.update(
                session, auth=auth, order_id=order_id, payload=payload
            )
            result = await InstallerWorkspaceService.manager_view(
                session, auth, order_id
            )
        return result
