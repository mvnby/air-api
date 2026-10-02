"""Shared guard used while the caller holds the intake entity row lock."""
from sqlalchemy.ext.asyncio import AsyncSession
from models.leads_inbox import InboxTriageState


async def require_unarchived_inbox(session: AsyncSession, entity_kind: str, entity_id: int) -> None:
    state = await session.get(InboxTriageState, (entity_kind, entity_id), populate_existing=True)
    if state is not None and state.archived_at is not None:
        raise ValueError("Обращение уже в архиве. Сначала восстановите его во входящих")
