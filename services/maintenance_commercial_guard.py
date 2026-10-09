"""Narrow guards against generic commands replacing explicit maintenance consent."""
from sqlmodel import select
from models import MaintenanceContinuation, MaintenanceOffer, MaintenanceOfferEvent


async def continuation_for(session, order_id):
    return await session.scalar(select(MaintenanceContinuation).where(MaintenanceContinuation.order_id == order_id))


async def approved_proposal_ids(session, order_id):
    rows = (await session.execute(select(MaintenanceOfferEvent).join(MaintenanceOffer, MaintenanceOffer.id == MaintenanceOfferEvent.offer_id)
        .join(MaintenanceContinuation, MaintenanceContinuation.id == MaintenanceOffer.continuation_id)
        .where(MaintenanceContinuation.order_id == order_id, MaintenanceOfferEvent.action == 'continue'))).scalars().all()
    return {row.details['approved_proposal_id'] for row in rows}


async def guard_proposal(session, order_id, proposal_id, *, selecting=False, status=None, archiving=False):
    if await continuation_for(session, order_id) is None:
        return
    approved = await approved_proposal_ids(session, order_id)
    if (selecting and approved) or proposal_id in approved or status in {'approved', 'accepted'}:
        raise ValueError('Согласованный состав ТО меняется только явной новой версией и согласием клиента')


async def guard_lines(session, order_id, proposal_id):
    if proposal_id in await approved_proposal_ids(session, order_id):
        raise ValueError('Согласованные строки ТО неизменяемы. Подготовьте новый вариант.')


async def guard_order_update(session, order, payload, fields):
    if await continuation_for(session, order.id) is None:
        return
    approved = await approved_proposal_ids(session, order.id)
    status = getattr(payload, 'status', None)
    if 'status' in fields and status != order.status and status in {'execution', 'closed'} and not approved:
        raise ValueError('Сначала сохраните согласие клиента и явно продолжите работы по ТО')
    if 'workflow_type' in fields and payload.workflow_type != 'repair':
        raise ValueError('Продолжение ТО сохраняет ремонтный сценарий')
    if 'proposal_status' in fields and payload.proposal_status != order.proposal_status:
        raise ValueError('Решение по ТО фиксируется в истории согласования')
    if 'auto_execution_on_payment' in fields and payload.auto_execution_on_payment:
        raise ValueError('Оплата не заменяет согласие по замечаниям ТО')
    if approved and {'target_currency', 'target_currency_amount'} & fields:
        if any(getattr(payload, key, None) != getattr(order, key, None) for key in fields & {'target_currency', 'target_currency_amount'}):
            raise ValueError('Валюта согласованного предложения неизменяема')
