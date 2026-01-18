from sqladmin import BaseView, expose

class CalendarAdmin(BaseView):
    name = "Календарь"
    icon = "fa-solid fa-calendar-days"
    
    @expose("/calendar", methods=["GET"])
    async def calendar_page(self, request):
        return await self.templates.TemplateResponse(
            request, 
            "sqladmin/calendar.html", 
            context={"request": request}
        )
