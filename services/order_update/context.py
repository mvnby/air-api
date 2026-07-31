"""Shared state for one Manager order update command."""

from dataclasses import dataclass
from typing import Any, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from models import Order
from services.tenant_scope_service import TenantScope


@dataclass
class OrderUpdateContext:
    session: AsyncSession
    order_id: int
    order: Order
    payload: Any
    tenant_scope: TenantScope
    fields_set: Set[str]
    previous_workflow_type: str
    previous_status: Any
    previous_negotiation_status: str
    previous_execution_status: str
    previous_delivery_address: Optional[str]
    currency_fields_changed: bool = False
    current_workflow_type: str = ""
