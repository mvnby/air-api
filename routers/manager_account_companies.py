from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from api_contracts.manager_companies import ManagerAccountCompaniesResponse
from core.database import get_session
from core.security import AuthenticatedIdentity, get_current_identity
from services.manager_account_companies_service import ManagerAccountCompaniesService

router = APIRouter(prefix="/api/manager/account", tags=["manager-account"])


@router.get("/companies", response_model=ManagerAccountCompaniesResponse, operation_id="manager_list_account_companies")
async def list_account_companies(
    page: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=100),
    session: AsyncSession = Depends(get_session), identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """Bootstrap active company choices from the authenticated person, ignoring selection headers.

    Actual memberships use current workspace roles; verified platform owners also see virtual
    support contexts without creating memberships. Invalid JWTs return401. Multiple companies
    require explicit selection on business requests, never on this account bootstrap.
    """
    return await ManagerAccountCompaniesService.list(session, identity=identity, page=page, limit=limit)
