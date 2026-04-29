from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from services.order_service import OrderService


router = APIRouter(tags=["admin-orders"])


class OrderStatusUpdate(BaseModel):
    order_id: int
    new_status: str


@router.post("/api/order/move")
async def move_order_status(
    data: OrderStatusUpdate,
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    API for Kanban drag-and-drop.
    """
    return await OrderService.update_status_from_admin(session, data.order_id, data.new_status)
