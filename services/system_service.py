import httpx
from core.config import settings
from core.logger import logger

class SystemService:
    @staticmethod
    async def trigger_web_rebuild(catalog_revision: int | None = None) -> dict:
        """
        Ask the standalone storefront to verify the requested catalog revision.
        Requires GITHUB_TOKEN with Actions access to the private web repository.
        """
        if not settings.GITHUB_TOKEN:
            logger.error("GITHUB_TOKEN is not set. Cannot trigger rebuild.")
            return {"success": False, "error": "GITHUB_TOKEN_MISSING"}

        owner = settings.WEB_REBUILD_GITHUB_OWNER
        repo = settings.WEB_REBUILD_GITHUB_REPO
        ref = settings.WEB_REBUILD_GITHUB_REF
        workflow_id = "rebuild-web.yml"
        
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches"
        
        headers = {
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        payload: dict[str, object] = {
            "ref": ref,
        }
        if catalog_revision is not None:
            payload["inputs"] = {"catalog_revision": str(max(0, int(catalog_revision)))}
        
        async with httpx.AsyncClient() as client:
            try:
                logger.info("Triggering storefront catalog sync for %s/%s at %s.", owner, repo, ref)
                response = await client.post(url, headers=headers, json=payload, timeout=10.0)
                
                if response.status_code == 204:
                    logger.info("Successfully triggered storefront catalog sync workflow.")
                    return {"success": True}
                else:
                    try:
                        error_data = response.json() if response.content else "No response body"
                    except ValueError:
                        error_data = response.text or "No response body"
                    logger.error(f"GitHub API Error ({response.status_code}): {error_data}")
                    return {
                        "success": False, 
                        "error": "GITHUB_API_ERROR", 
                        "status_code": response.status_code,
                        "details": error_data
                    }
            except Exception as e:
                logger.exception(f"Unexpected error triggering GitHub rebuild: {e}")
                return {"success": False, "error": str(e)}

system_service = SystemService()
