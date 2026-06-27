from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import GET_MANAGER_CATALOG_QUALITY_REPORT
from schemas import ManagerCatalogQualityReportResponse
from services.catalog_quality_service import CatalogQualityService


router = APIRouter(prefix="/api/manager/catalog-quality", tags=["manager catalog quality"])


@router.get(
    "/report",
    response_model=ManagerCatalogQualityReportResponse,
    operation_id=GET_MANAGER_CATALOG_QUALITY_REPORT,
)
async def get_manager_catalog_quality_report(
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    q: Optional[str] = Query(None),
    category: Optional[Literal["media", "identity", "specs", "commerce", "supplier"]] = Query(None),
    severity: Optional[Literal["critical", "warning", "info"]] = Query(None),
    issue_code: Optional[str] = Query(None),
    only_problems: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await CatalogQualityService.build_report(
        session=session,
        page=page,
        limit=limit,
        q=q,
        category=category,
        severity=severity,
        issue_code=issue_code,
        only_problems=only_problems,
    )
