from sqladmin import BaseView, expose
from starlette.responses import RedirectResponse
from services.google_service import get_google_service

class GoogleAuthView(BaseView):
    name = "Google Integration"
    icon = "fa-brands fa-google"

    @expose("/google_auth", methods=["GET"])
    async def index(self, request):
        status = get_google_service().get_token_status()
        return await self.templates.TemplateResponse(
            request, 
            "sqladmin/google_auth.html", 
            {"status": status, "model_view": self}
        )

    @expose("/google_auth/url", methods=["GET", "POST"])
    async def auth_url(self, request):
        try:
            url = get_google_service().get_auth_url()
            return RedirectResponse(url=url, status_code=303)
        except Exception as e:
            return await self.templates.TemplateResponse(
                request,
                "sqladmin/google_auth.html",
                {
                    "status": get_google_service().get_token_status(),
                    "model_view": self,
                    "error": f"Error generating URL: {str(e)}"
                }
            )

    @expose("/google_auth/exchange", methods=["POST"])
    async def exchange_code(self, request):
        form = await request.form()
        code = form.get("code")
        
        if not code:
            return RedirectResponse(
                url=request.url_for("admin:index"), 
                status_code=303
            )

        try:
            get_google_service().finish_auth(code)
            # Redirect back to index with success? 
            # SQLAdmin doesn't have built-in flash messages easily accessible in custom views without setup,
            # but we can just redirect and the status will show green.
            return RedirectResponse(
                url=request.url_for("admin:index"), 
                status_code=303
            )
        except Exception as e:
             status = get_google_service().get_token_status()
             return await self.templates.TemplateResponse(
                request,
                "sqladmin/google_auth.html",
                {
                    "status": status,
                    "model_view": self,
                    "error": f"Error exchanging code: {str(e)}"
                }
            )
