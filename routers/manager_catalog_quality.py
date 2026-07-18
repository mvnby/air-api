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
    equipment_type: Optional[str] = Query(None),
    equipment_subtype: Optional[str] = Query(None),
    brand_id: Optional[int] = Query(None, ge=1),
    series_id: Optional[int] = Query(None, ge=1),
    series_state: Optional[Literal["assigned", "missing"]] = Query(None),
    supplier_id: Optional[int] = Query(None, ge=1),
    supplier_state: Optional[Literal["mapped", "in_stock", "unmapped", "multiple"]] = Query(None),
    publication: Optional[Literal["published", "hidden"]] = Query(None),
    availability: Optional[Literal["in_stock", "out_of_stock"]] = Query(None),
    priority: Optional[Literal["high", "medium", "low"]] = Query(None),
    score_min: Optional[int] = Query(None, ge=0, le=100),
    score_max: Optional[int] = Query(None, ge=0, le=100),
    only_fixable: bool = Query(False),
    sort_by: Literal[
        "priority", "score_asc", "critical", "stock", "newest", "title", "brand", "series"
    ] = Query("priority"),
    group_by: Literal[
        "none", "brand", "series", "supplier", "equipment_type"
    ] = Query("none"),
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
        equipment_type=equipment_type,
        equipment_subtype=equipment_subtype,
        brand_id=brand_id,
        series_id=series_id,
        series_state=series_state,
        supplier_id=supplier_id,
        supplier_state=supplier_state,
        publication=publication,
        availability=availability,
        priority=priority,
        score_min=score_min,
        score_max=score_max,
        only_fixable=only_fixable,
        sort_by=sort_by,
        group_by=group_by,
    )
