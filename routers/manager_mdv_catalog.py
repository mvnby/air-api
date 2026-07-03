from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from parsers.mdv_catalog import MDV_EXPORT_URLS
from routers.manager_operation_ids import (
    PREVIEW_MDV_CATALOG_IMPORT,
    START_MDV_CATALOG_IMPORT_JOB,
)
from schemas import (
    CatalogImportJobStartResponse,
    MdvCatalogImportPayload,
    MdvCatalogPreviewPayload,
    MdvCatalogPreviewResponse,
)
from services.catalog_import_runtime_service import catalog_import_runtime_service
from services.mdv_catalog_preview_service import MdvCatalogPreviewService
from services.mdv_legacy_replace_service import MdvLegacyReplaceService


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.post(
    "/catalog/mdv/preview",
    response_model=MdvCatalogPreviewResponse,
    operation_id=PREVIEW_MDV_CATALOG_IMPORT,
)
async def preview_mdv_catalog_import(
    payload: MdvCatalogPreviewPayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Build a dry-run report for official MDV exports before writing products.
    """
    report = await MdvCatalogPreviewService.build_preview(
        session,
        catalogs=payload.catalogs,
        sample_limit=payload.sample_limit,
        replace_legacy_catalogs=payload.replace_legacy_catalogs,
    )
    return MdvCatalogPreviewResponse(**report)


@router.post(
    "/catalog/mdv/import/jobs",
    response_model=CatalogImportJobStartResponse,
    operation_id=START_MDV_CATALOG_IMPORT_JOB,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_mdv_catalog_import_job(
    payload: MdvCatalogImportPayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Start an official MDV catalog refresh in the existing background queue.
    """
    replace_catalogs = MdvLegacyReplaceService.normalize_catalogs(
        payload.replace_legacy_catalogs
    )
    if replace_catalogs:
        await MdvLegacyReplaceService.execute(session, catalogs=replace_catalogs)

    catalogs = MdvCatalogPreviewService.normalize_catalogs(payload.catalogs)
    urls = [MDV_EXPORT_URLS[catalog] for catalog in catalogs]
    job = await catalog_import_runtime_service.start_import(
        urls=urls,
        with_related=False,
        update_existing=payload.update_existing,
    )
    return CatalogImportJobStartResponse(
        job_id=job["job_id"],
        status=job["status"],
        stage=job["stage"],
    )
