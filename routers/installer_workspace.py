"""Authenticated GET-only installer work surface."""

from contextlib import asynccontextmanager
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.installer_workspace import (
    InstallerWorkDetail,
    InstallerWorksResponse,
)
from core.database import get_session
from core.security import AuthenticatedUser, get_current_installer_context
from services.installer_collection_service import InstallerWorkspaceError
from services.installer_material_service import InstallerMaterialService
from services.installer_workspace_service import InstallerWorkspaceService
from services.worker_assignment_service import WorkerAssignmentError

router = APIRouter(prefix="/api/installer", tags=["installer-work"])


@asynccontextmanager
async def installer_errors(session):
    try:
        yield
    except (InstallerWorkspaceError, WorkerAssignmentError) as exc:
        await session.rollback()
        raise HTTPException(
            exc.status_code, detail={"code": exc.code, "message": str(exc)}
        ) from None


@router.get(
    "/works", response_model=InstallerWorksResponse, operation_id="list_installer_works"
)
async def list_works(
    response: Response,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    bucket: str = Query("all", pattern="^(all|today|upcoming|unscheduled)$"),
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Read only the actor's live explicit work assignments in the selected company/site.

    Active account, actual membership, worker profile, assignment and work lifecycle
    are rechecked. Payroll-only or historical links never grant access. Date filters
    precede count/pagination; limit is at most 100. Financial/private CRM fields are
    absent. See https://github.com/mvnby/air-api/blob/main/docs/installer-workspace.md.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await InstallerWorkspaceService.list_works(
            session, auth, page, limit, bucket
        )


@router.get(
    "/works/{assignment_id}",
    response_model=InstallerWorkDetail,
    operation_id="get_installer_work",
)
async def read_work(
    assignment_id: int,
    response: Response,
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Read a live assigned task with approved instructions, technical equipment and materials.

    Missing, revoked, foreign-company/site or inactive work returns404. No raw order
    comments, quotes, payment ledger, supplier, purchase price or cost is returned.
    Collection amount is visible only to the designated recipient while its financial
    snapshot is current. See the installer-workspace domain contract.
    """
    response.headers["Cache-Control"] = "private, no-store"
    async with installer_errors(session):
        return await InstallerWorkspaceService.detail(session, auth, assignment_id)


@router.get(
    "/works/{assignment_id}/materials/{material_id}/content",
    operation_id="read_installer_work_material",
)
async def read_material(
    assignment_id: int,
    material_id: int,
    auth: AuthenticatedUser = Depends(get_current_installer_context),
    session: AsyncSession = Depends(get_session),
):
    """Proxy explicitly published technical bytes after live assignment/link checks.

    ACL is rechecked after storage I/O. No bearer/presigned URL is issued, caching is
    disabled and conditional304 cannot bypass authorization. Archived, unpublished,
    revoked or foreign materials return404. Original filenames/source metadata are
    never exposed; only approved image/PDF media are allowed.
    """
    async with installer_errors(session):
        content, mime, filename, kind = await InstallerMaterialService.read_content(
            session, auth=auth, assignment_id=assignment_id, material_id=material_id
        )
        return Response(
            content,
            media_type=mime,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
                "Content-Disposition": f'{"inline" if kind == "image" else "attachment"}; filename="{filename}"',
            },
        )
