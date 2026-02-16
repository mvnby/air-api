"""Belarus proxy endpoints split from the main API router."""

from fastapi import APIRouter, Depends, Query

from core.security import get_current_username
from services.proxy_lookup_service import ProxyLookupService

router = APIRouter(tags=["api"])


@router.get("/admin/proxy/egr")
async def proxy_egr(
    unp: str,
    username: str = Depends(get_current_username),
):
    """Proxy for Belarus EGR (Ministry of Taxes) API."""
    return await ProxyLookupService.fetch_egr_data(unp)


@router.get("/admin/proxy/bank")
async def find_bank(
    search: str = Query(None, description="BIC код или IBAN"),
    username: str = Depends(get_current_username),
):
    """Find bank in NBRB reference by BIC/IBAN."""
    return await ProxyLookupService.find_bank(
        search,
        include_all_on_empty=True,
        include_debug=True,
    )


@router.get("/v1/proxy/egr")
async def public_proxy_egr(unp: str):
    """Public proxy for Belarus EGR (Ministry of Taxes) API."""
    return await ProxyLookupService.fetch_egr_data(unp)


@router.get("/v1/proxy/bank")
async def public_find_bank(search: str = Query(None, description="BIC код или IBAN")):
    """Public proxy to find bank details by IBAN/BIC."""
    return await ProxyLookupService.find_bank(
        search,
        include_all_on_empty=False,
        include_debug=False,
    )
