"""One parent revision for waiting, relevant order updates, payments and stages."""

from sqlalchemy import update
from sqlalchemy.orm.attributes import set_committed_value
from models import Order


async def bump_order_workflow_revision(session, order_or_id):
    """Caller owns the transaction and locks the parent before children.

    Use an atomic SQL increment, so a reused ORM identity cannot overwrite a
    revision advanced by an earlier serialized command. This is never a reader.
    """
    order_id = order_or_id if isinstance(order_or_id, int) else order_or_id.id
    await session.flush()
    revision = (
        await session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(workflow_revision=Order.workflow_revision + 1)
            .returning(Order.workflow_revision)
            .execution_options(synchronize_session=False)
        )
    ).scalar_one()
    if not isinstance(order_or_id, int):
        set_committed_value(order_or_id, "workflow_revision", revision)
    return revision
