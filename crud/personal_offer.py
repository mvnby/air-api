from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from models.personal_offer import PersonalOffer, PersonalOfferPublication
from models.tenancy import TenantScope


class PersonalOfferDAO:
    @staticmethod
    def scope_filters(scope: TenantScope):
        return PersonalOffer.tenant_id == scope.tenant_id, PersonalOffer.storefront_id == scope.storefront_id

    @classmethod
    async def get(
        cls, session: AsyncSession, offer_id: int, scope: TenantScope, *, lock: bool = False,
    ) -> PersonalOffer | None:
        statement = select(PersonalOffer).where(PersonalOffer.id == offer_id, *cls.scope_filters(scope))
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await session.execute(statement)).scalar_one_or_none()

    @classmethod
    async def list(
        cls, session: AsyncSession, scope: TenantScope, *, order_id: int | None, limit: int,
        before_id: int | None,
    ):
        statement = select(PersonalOffer, PersonalOfferPublication).outerjoin(
            PersonalOfferPublication,
            and_(
                PersonalOfferPublication.offer_id == PersonalOffer.id,
                PersonalOfferPublication.revoked_at.is_(None),
            ),
        ).where(*cls.scope_filters(scope)).options(load_only(
            PersonalOfferPublication.hostname, PersonalOfferPublication.encrypted_token,
            PersonalOfferPublication.expires_at,
        ))
        if order_id is not None:
            statement = statement.where(PersonalOffer.order_id == order_id)
        if before_id is not None:
            statement = statement.where(PersonalOffer.id < before_id)
        result = await session.execute(statement.order_by(PersonalOffer.id.desc()).limit(limit + 1))
        return result.all()

    @staticmethod
    async def current(session: AsyncSession, offer_id: int) -> PersonalOfferPublication | None:
        statement = select(PersonalOfferPublication).where(
            PersonalOfferPublication.offer_id == offer_id,
            PersonalOfferPublication.revoked_at.is_(None),
        )
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def get_publish_version(session: AsyncSession, offer_id: int, request_id: str) -> int | None:
        statement = select(PersonalOfferPublication.draft_version).where(
            PersonalOfferPublication.offer_id == offer_id,
            PersonalOfferPublication.request_id == request_id,
        )
        return (await session.execute(statement)).scalar_one_or_none()

    @classmethod
    async def public_snapshot(
        cls, session: AsyncSession, *, scope: TenantScope, hostname: str, token_digest: str, now: datetime,
    ) -> dict | None:
        statement = select(PersonalOfferPublication.snapshot).join(
            PersonalOffer, PersonalOffer.id == PersonalOfferPublication.offer_id,
        ).where(
            *cls.scope_filters(scope),
            PersonalOfferPublication.hostname == hostname,
            PersonalOfferPublication.token_digest == token_digest,
            PersonalOfferPublication.revoked_at.is_(None),
            PersonalOfferPublication.expires_at > now,
        )
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def add(session: AsyncSession, row: PersonalOffer | PersonalOfferPublication) -> None:
        session.add(row)
        await session.flush()
