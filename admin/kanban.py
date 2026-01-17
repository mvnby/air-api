
from sqladmin import BaseView, expose
from core.database import async_session_maker
from services.order_service import OrderService
from models import OrderStatus
from datetime import datetime

class KanbanView(BaseView):
    name = "Kanban Board"
    icon = "fa-solid fa-table-columns"
    route_name = "kanban"

    @expose("/kanban", methods=["GET"])
    async def kanban_page(self, request):
        async with async_session_maker() as session:
            orders = await OrderService.get_all_orders(session)
        
        # Group orders by status
        orders_by_status = {status.value: [] for status in OrderStatus}
        
        # Sort keys to match Enum order (Pipeline flow)
        # Using the Enum members order
        statuses = {status.value: status.value.replace('_', ' ').title() for status in OrderStatus}
        
        for order in orders:
            # Handle case where status might be legacy or string
            status_val = order.status.value if hasattr(order.status, 'value') else order.status
            if status_val in orders_by_status:
                orders_by_status[status_val].append(order)
            else:
                # Fallback for unknown status
                if 'new_lead' in orders_by_status:
                    orders_by_status['new_lead'].append(order)
        
        return await self.templates.TemplateResponse(
            request, 
            "sqladmin/kanban.html", 
            context={
                "orders": orders_by_status,
                "statuses": statuses,
                "now": datetime.now()
            }
        )
