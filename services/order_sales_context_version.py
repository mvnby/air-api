"""Fingerprint the source context of one native sales proposal.

Callers must lock the order before comparing or freezing this version. Document
parameters are deliberately excluded: their own native revision controls edits.
"""

import hashlib
import json

from sqlmodel import select

from models import Order
from services.order_proposal_version import proposal_version


async def sales_order_context_version(session, order_id: int, proposal_id: int) -> str:
    commercial_version = await proposal_version(session, order_id, proposal_id)
    order = (await session.execute(
        select(Order).where(Order.id == order_id).execution_options(populate_existing=True)
    )).scalar_one()
    context = ((order.technical_meta or {}).get("sales_selections") or {}).get(str(proposal_id))
    value = [commercial_version, order.workflow_revision, order.title, order.comment,
             order.delivery_address, context]
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
