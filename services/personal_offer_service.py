"""Tenant-scoped personal offer drafts and transactional link publication."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import re
from secrets import token_urlsafe

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.personal_offers import (
    ManagerPersonalOfferListResponse,
    ManagerPersonalOfferPublished,
    ManagerPersonalOfferResponse,
    PersonalOfferDraftInput,
    PersonalOfferPublishInput,
    PersonalOfferRoomInput,
    PersonalOfferUpdateInput,
    PublicPersonalOfferResponse,
)
from core.config import settings
from core.integration_credential_keyring import (
    IntegrationCredentialUnavailable,
    IntegrationCredentialUnreadable,
    InvalidIntegrationCredentialKeyring,
)
from crud.personal_offer import PersonalOfferDAO
from crud.tenancy import TenancyDAO
from models import OrderStatus
from models.personal_offer import PersonalOffer, PersonalOfferPublication
from models.tenancy import TenantScope, utc_now
from services.command_transaction import command_transaction
from services.personal_offer_projection import PersonalOfferProjection
from services.storefront_context_service import StorefrontContextService
from services.tenant_entity_access_service import TenantEntityAccessService


_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def _with_timezone(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _token_context(offer: PersonalOffer) -> bytes:
    return f"mvn.personal-offer.token.v1:{offer.tenant_id}:{offer.storefront_id}:{offer.id}".encode("ascii")


def _encrypt_token(token: str, offer: PersonalOffer) -> str:
    try:
        keyring = settings.integration_credential_keyring
        context = _token_context(offer)
        raw = token.encode("ascii")
        if keyring.enabled and keyring.write_mode == "active":
            return keyring.encrypt(raw, context=context)
        return keyring.encrypt_legacy(raw, context=context, local_legacy_secret=settings.SECRET_KEY)
    except (IntegrationCredentialUnavailable, InvalidIntegrationCredentialKeyring) as exc:
        raise HTTPException(503, "Временно не удалось создать ссылку.") from exc


def _decrypt_token(ciphertext: str, offer: PersonalOffer) -> str:
    try:
        return settings.integration_credential_keyring.decrypt(
            ciphertext, context=_token_context(offer), local_legacy_secret=settings.SECRET_KEY,
        ).plaintext.decode("ascii")
    except (IntegrationCredentialUnreadable, InvalidIntegrationCredentialKeyring, UnicodeError) as exc:
        raise HTTPException(503, "Временно не удалось прочитать ссылку.") from exc


def _token_digest(token: str) -> str:
    return sha256(token.encode("ascii")).hexdigest()


def _require_expected_version(offer: PersonalOffer, expected_version: int) -> None:
    if offer.version != expected_version:
        raise HTTPException(409, "Предложение обновилось. Откройте актуальную версию.")


def _require_future_expiry(value: datetime) -> None:
    if value <= utc_now():
        raise HTTPException(422, "Срок действия предложения должен быть в будущем.")


def _draft_rooms(offer: PersonalOffer) -> list[PersonalOfferRoomInput]:
    return [PersonalOfferRoomInput.model_validate(room) for room in offer.rooms]


def _draft_response(
    offer: PersonalOffer, publication: PersonalOfferPublication | None,
) -> ManagerPersonalOfferResponse:
    published = None
    if publication is not None and _with_timezone(publication.expires_at) > utc_now():
        token = _decrypt_token(publication.encrypted_token, offer)
        published = ManagerPersonalOfferPublished(
            url=f"https://{publication.hostname}/predlozhenie/{token}/",
            expires_at=_with_timezone(publication.expires_at),
        )
    return ManagerPersonalOfferResponse(
        id=offer.id, version=offer.version, order_id=offer.order_id,
        expires_at=_with_timezone(offer.expires_at), rooms=_draft_rooms(offer), published=published,
    )


class PersonalOfferService:
    @staticmethod
    async def _get(
        session: AsyncSession, offer_id: int, scope: TenantScope, *, lock: bool = False,
    ) -> PersonalOffer:
        offer = await PersonalOfferDAO.get(session, offer_id, scope, lock=lock)
        if offer is None:
            raise HTTPException(404, "Предложение не найдено.")
        return offer

    @classmethod
    async def get(cls, session: AsyncSession, offer_id: int, scope: TenantScope) -> ManagerPersonalOfferResponse:
        offer = await cls._get(session, offer_id, scope)
        return _draft_response(offer, await PersonalOfferDAO.current(session, offer_id))

    @staticmethod
    async def list(
        session: AsyncSession, scope: TenantScope, *, order_id: int | None, limit: int, before_id: int | None,
    ) -> ManagerPersonalOfferListResponse:
        rows = await PersonalOfferDAO.list(
            session, scope, order_id=order_id, limit=limit, before_id=before_id,
        )
        return ManagerPersonalOfferListResponse(
            items=[_draft_response(offer, publication) for offer, publication in rows[:limit]],
            has_more=len(rows) > limit,
        )

    @staticmethod
    async def create(
        session: AsyncSession, scope: TenantScope, draft: PersonalOfferDraftInput,
    ) -> ManagerPersonalOfferResponse:
        _require_future_expiry(draft.expires_at)
        async with command_transaction(session):
            if draft.order_id is not None:
                order = await TenantEntityAccessService.get_order(
                    session, draft.order_id, tenant_scope=scope, for_update=True,
                )
                if order is None:
                    raise HTTPException(404, "Заказ не найден.")
                if order.status != OrderStatus.NEGOTIATION:
                    raise HTTPException(409, "Предложение можно привязать к заказу в «Переговорах».")
            await PersonalOfferProjection.visible_products(session, draft.rooms, scope)
            offer = PersonalOffer(
                tenant_id=scope.tenant_id,
                storefront_id=scope.storefront_id,
                order_id=draft.order_id,
                expires_at=draft.expires_at,
                rooms=[room.model_dump(mode="json") for room in draft.rooms],
            )
            await PersonalOfferDAO.add(session, offer)
            return _draft_response(offer, None)

    @classmethod
    async def update(
        cls, session: AsyncSession, offer_id: int, scope: TenantScope, draft: PersonalOfferUpdateInput,
    ) -> ManagerPersonalOfferResponse:
        _require_future_expiry(draft.expires_at)
        async with command_transaction(session):
            offer = await cls._get(session, offer_id, scope, lock=True)
            _require_expected_version(offer, draft.expected_version)
            if (
                offer.rooms and offer.rooms[0].get("selection_mode") == "package"
                and any("selection_mode" not in room.model_fields_set for room in draft.rooms)
            ):
                raise HTTPException(409, "Обновите страницу Manager перед сохранением комплектов.")
            if "order_id" in draft.model_fields_set and draft.order_id != offer.order_id:
                raise HTTPException(409, "Связь предложения с заказом задаётся при создании.")
            await PersonalOfferProjection.visible_products(session, draft.rooms, scope)
            offer.rooms = [room.model_dump(mode="json") for room in draft.rooms]
            offer.expires_at = draft.expires_at
            offer.updated_at = utc_now()
            offer.version += 1
            return _draft_response(offer, await PersonalOfferDAO.current(session, offer_id))

    @staticmethod
    async def _project(
        session: AsyncSession, offer: PersonalOffer, scope: TenantScope,
    ) -> PublicPersonalOfferResponse:
        rooms = _draft_rooms(offer)
        visible = await PersonalOfferProjection.visible_products(session, rooms, scope)
        return PersonalOfferProjection.build(rooms, _with_timezone(offer.expires_at), visible)

    @classmethod
    async def preview(cls, session: AsyncSession, offer_id: int, scope: TenantScope) -> PublicPersonalOfferResponse:
        return await cls._project(session, await cls._get(session, offer_id, scope), scope)

    @classmethod
    async def publish(
        cls, session: AsyncSession, offer_id: int, scope: TenantScope, command: PersonalOfferPublishInput,
    ) -> ManagerPersonalOfferResponse:
        request_id = str(command.request_id)
        async with command_transaction(session):
            offer = await cls._get(session, offer_id, scope, lock=True)
            publication = await PersonalOfferDAO.current(session, offer_id)
            prior_version = await PersonalOfferDAO.get_publish_version(session, offer_id, request_id)
            if prior_version is not None:
                if prior_version != command.expected_version:
                    raise HTTPException(409, "Этот запрос уже использовался для другой версии предложения.")
                return _draft_response(offer, publication)
            _require_expected_version(offer, command.expected_version)
            _require_future_expiry(_with_timezone(offer.expires_at))
            domains = await TenancyDAO.active_primary_domains(session, storefront_ids=[scope.storefront_id])
            hostname = domains.get(scope.storefront_id)
            if hostname is None:
                raise HTTPException(409, "У витрины нет подтверждённого основного домена.")
            hostname = StorefrontContextService.normalize_hostname(hostname)
            projection = await cls._project(session, offer, scope)
            token = token_urlsafe(32)
            if publication is not None:
                publication.revoked_at = utc_now()
                await session.flush()
            publication = PersonalOfferPublication(
                offer_id=offer_id, request_id=request_id, draft_version=offer.version, hostname=hostname,
                token_digest=_token_digest(token), encrypted_token=_encrypt_token(token, offer),
                expires_at=offer.expires_at, snapshot=projection.model_dump(mode="json"),
            )
            await PersonalOfferDAO.add(session, publication)
            offer.updated_at = utc_now()
            offer.version += 1
            return _draft_response(offer, publication)

    @classmethod
    async def revoke(
        cls, session: AsyncSession, offer_id: int, scope: TenantScope, expected_version: int,
    ) -> ManagerPersonalOfferResponse:
        async with command_transaction(session):
            offer = await cls._get(session, offer_id, scope, lock=True)
            publication = await PersonalOfferDAO.current(session, offer_id)
            if publication is not None:
                _require_expected_version(offer, expected_version)
                publication.revoked_at = utc_now()
                offer.updated_at = publication.revoked_at
                offer.version += 1
            return _draft_response(offer, None)

    @staticmethod
    async def read_public(
        session: AsyncSession, scope: TenantScope, hostname: str, token: str,
    ) -> PublicPersonalOfferResponse | None:
        if _TOKEN.fullmatch(token) is None:
            return None
        data = await PersonalOfferDAO.public_snapshot(
            session, scope=scope, hostname=hostname, token_digest=_token_digest(token), now=utc_now(),
        )
        return PublicPersonalOfferResponse.model_validate(data) if data is not None else None
