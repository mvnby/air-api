from sqlalchemy import func
from sqlmodel import select
from models.staff_invitation import StaffInvitation


class StaffInvitationDAO:
    @staticmethod
    async def by_hash(session, token_hash, *, lock=False):
        statement = select(StaffInvitation).where(StaffInvitation.token_hash == token_hash).execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @staticmethod
    async def list(session, *, tenant_id, page, limit):
        condition = StaffInvitation.tenant_id == tenant_id
        total = await session.scalar(select(func.count()).select_from(StaffInvitation).where(condition))
        items = (await session.execute(select(StaffInvitation).where(condition).order_by(StaffInvitation.id.desc())
                                       .offset((page - 1) * limit).limit(limit))).scalars().all()
        return items, total
