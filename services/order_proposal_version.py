"""Fingerprint one proposal's persisted commercial state.

Callers comparing or producing a coherent snapshot must first lock its order,
which is the shared serialization boundary of Manager commercial commands.
"""

import hashlib
import json

from sqlalchemy.inspection import inspect
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Order, OrderProductLink, OrderProposal, OrderServiceLink


def _columns(row):
    return {column.key: getattr(row, column.key) for column in inspect(type(row)).columns}


async def proposal_version(session, order_id: int, proposal_id: int) -> str:
    order_query = select(Order).where(Order.id == order_id).execution_options(populate_existing=True)
    proposal_query = (
        select(OrderProposal)
        .where(OrderProposal.id == proposal_id, OrderProposal.order_id == order_id)
        .execution_options(populate_existing=True)
    )
    product_query = (
        select(OrderProductLink)
        .options(selectinload(OrderProductLink.product))
        .where(OrderProductLink.order_id == order_id, OrderProductLink.proposal_id == proposal_id)
        .order_by(OrderProductLink.id)
        .execution_options(populate_existing=True)
    )
    service_query = (
        select(OrderServiceLink)
        .options(selectinload(OrderServiceLink.service))
        .where(OrderServiceLink.order_id == order_id, OrderServiceLink.proposal_id == proposal_id)
        .order_by(OrderServiceLink.id)
        .execution_options(populate_existing=True)
    )
    order = (await session.execute(order_query)).scalar_one()
    proposal = (await session.execute(proposal_query)).scalar_one()
    products = (await session.execute(product_query)).scalars().all()
    services = (await session.execute(service_query)).scalars().all()
    order_fields = {
        name: getattr(order, name)
        for name in ("customer_id", "target_currency", "target_currency_amount", "workflow_type")
    }
    state = [
        order_fields,
        {"id": proposal.id, "status": proposal.status, "is_archived": proposal.is_archived},
        [(_columns(row), row.product.title if row.product else None) for row in products],
        [(_columns(row), row.service.title if row.service else None) for row in services],
    ]
    encoded = json.dumps(state, sort_keys=True, default=str, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()
