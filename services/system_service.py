import httpx
from core.config import settings
from core.logger import logger

class SystemService:
    @staticmethod
    async def trigger_web_rebuild() -> dict:
        """
        Triggers the 'rebuild-web.yml' workflow in GitHub Actions.
        Requires GITHUB_TOKEN to be set in .env.
        """
        if not settings.GITHUB_TOKEN:
            logger.error("GITHUB_TOKEN is not set. Cannot trigger rebuild.")
            return {"success": False, "error": "GITHUB_TOKEN_MISSING"}

        owner = settings.GITHUB_OWNER
        repo = settings.GITHUB_REPO
        workflow_id = "rebuild-web.yml"
        
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches"
        
        headers = {
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        payload = {
            "ref": "main" # Build from main branch
        }
        
        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Triggering GitHub rebuild for {owner}/{repo}...")
                response = await client.post(url, headers=headers, json=payload, timeout=10.0)
                
                if response.status_code == 204:
                    logger.info("Successfully triggered rebuild-web workflow.")
                    return {"success": True}
                else:
                    error_data = response.json() if response.content else "No response body"
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
