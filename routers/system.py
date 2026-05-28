from fastapi import APIRouter, Depends, HTTPException
from core.security import get_current_username
from services.system_service import system_service
from core.logger import logger

router = APIRouter(prefix="/api/system", tags=["system"])

@router.post("/rebuild-web")
async def trigger_rebuild_web(username: str = Depends(get_current_username)):
    """
    Trigger a turbo-rebuild of the frontend Astro site.
    Accessible only by authenticated managers/admins.
    """
    logger.info(f"User {username} triggered a web site rebuild.")
    
    result = await system_service.trigger_web_rebuild()
    
    if not result["success"]:
        # Handle specific known errors
        if result["error"] == "GITHUB_TOKEN_MISSING":
            raise HTTPException(
                status_code=503, 
                detail="GitHub integration not configured on server (.env missing GITHUB_TOKEN)"
            )
        
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to trigger rebuild: {result.get('error')}"
        )
        
    return {"message": "Rebuild triggered successfully. The site will be updated in ~2 minutes."}
@router.get("/health", include_in_schema=False)
async def health():
    return {
        "ok": True,
        "service": "air-api"
    }
