"""Persist one multi-split decision as one editable order proposal."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.multi_split import ManagerMultiSplitSavePayload
from models import OrderMultiSplitConfiguration, OrderProductLink, OrderProposal
from models.tenancy import TenantScope
from services.command_transaction import command_transaction
from services.multi_split_configuration_service import MultiSplitConfigurationService
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_proposal_lifecycle import normalize_proposal_status
from services.order_service import OrderService


class MultiSplitProposalService:
    @staticmethod
    async def save(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        order_id: int,
        payload: ManagerMultiSplitSavePayload,
    ) -> dict:
        async with command_transaction(session):
            order = await OrderProposalCommandService._load_order_for_write(
                session, order_id, tenant_scope=tenant_scope,
            )
            if OrderService._status_value(order.status) != "negotiation":
                raise ValueError("Мультисплит можно добавить только в заказ на этапе переговоров.")
            preview = await MultiSplitConfigurationService.preview(
                session, tenant_scope=tenant_scope, request=payload,
            )
            if (
                preview.public.status != payload.expected_status
                or [item.model_dump() for item in preview.public.components]
                != [item.model_dump() for item in payload.expected_components]
            ):
                raise MultiSplitStalePreviewError("Цена, наличие или статус изменились. Пересчитайте конфигурацию перед сохранением.")
            if preview.public.status == "incompatible":
                raise ValueError("Подтверждённый профиль исключает выбранный состав.")

            if payload.proposal_id is not None:
                proposal = next((item for item in order.proposals if item.id == payload.proposal_id and not item.is_archived), None)
                if proposal is None:
                    raise ValueError("Вариант предложения не найден в этом заказе.")
                if normalize_proposal_status(proposal.status) != "draft":
                    raise ValueError("Изменять можно только черновик предложения.")
                if any(link.proposal_id == proposal.id for link in [*order.product_links, *order.service_links]):
                    raise ValueError("В варианте уже есть строки. Сохраните конфигурацию отдельной альтернативой.")
                existing_configuration = (await session.execute(
                    select(OrderMultiSplitConfiguration.id).where(OrderMultiSplitConfiguration.proposal_id == proposal.id)
                )).scalar_one_or_none()
                if existing_configuration is not None:
                    raise ValueError("В этом варианте уже сохранена конфигурация. Создайте отдельную альтернативу.")
            else:
                active_count = len([item for item in order.proposals if not item.is_archived])
                proposal = OrderProposal(
                    order_id=order_id,
                    name=f"Мультисплит · вариант {active_count + 1}",
                    status="draft",
                    is_selected=False,
                    sort_order=active_count * 10,
                )
                session.add(proposal)
                await session.flush()

            for item in preview.public.components:
                metric = preview.metrics.get(item.product_id, {})
                raw_cost = metric.get("min_cost_byn")
                session.add(OrderProductLink(
                    order_id=order_id,
                    proposal_id=int(proposal.id),
                    product_id=item.product_id,
                    quantity=item.quantity,
                    price=item.unit_price_byn,
                    cost=int(round(float(raw_cost))) if raw_cost is not None else 0,
                    title_snapshot=item.title,
                    currency_snapshot="BYN",
                ))
            await session.flush()
            profile = preview.profile
            config = OrderMultiSplitConfiguration(
                proposal_id=int(proposal.id),
                order_id=order_id,
                rooms=[room.model_dump() for room in payload.rooms],
                component_snapshot=[item.model_dump() for item in preview.public.components],
                verification_status=preview.public.status,
                profile_id=int(profile.id) if profile is not None else None,
                profile_version=profile.version if profile is not None else None,
                source_url=profile.source_url if profile is not None else None,
                source_version=profile.source_version if profile is not None else None,
            )
            session.add(config)
            await OrderService._refresh_order_financials(session, order)
            session.add(order)

        return await OrderProposalCommandService._project_committed_order(
            session, order_id, tenant_scope=tenant_scope,
        )


class MultiSplitStalePreviewError(ValueError):
    """The accepted preview no longer matches the current catalog."""
