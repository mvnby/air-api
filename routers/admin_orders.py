from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.database import async_session_maker
from core.security import get_current_username


router = APIRouter(tags=["admin-orders"])


class OrderStatusUpdate(BaseModel):
    order_id: int
    new_status: str


@router.post("/api/order/move")
async def move_order_status(
    data: OrderStatusUpdate,
    username: str = Depends(get_current_username)
):
    """
    API for Kanban drag-and-drop.
    """
    from services.order_service import OrderService
    from models import OrderStatus

    async with async_session_maker() as session:
        try:
            status_enum = None
            for status in OrderStatus:
                if status.value == data.new_status:
                    status_enum = status
                    break

            if not status_enum:
                return {"success": False, "error": f"Invalid status: {data.new_status}"}

            success = await OrderService.update_status(session, data.order_id, status_enum)
            return {"success": success}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
