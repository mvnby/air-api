import logging
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import ServiceTariff, ServiceTariffRule
from schemas import (
    ManagerTariffCreatePayload,
    ManagerTariffRuleCreatePayload,
    ManagerTariffRuleUpdatePayload,
    ManagerTariffServiceKind,
    ManagerTariffUpdatePayload,
)

logger = logging.getLogger(__name__)


class TariffsService:
    @staticmethod
    async def get_all_tariffs(
        session: AsyncSession,
        service_kind: Optional[ManagerTariffServiceKind] = None,
        include_inactive: bool = True,
    ) -> List[ServiceTariff]:
        stmt = select(ServiceTariff).options(selectinload(ServiceTariff.rules))
        if service_kind is not None:
            stmt = stmt.where(ServiceTariff.service_kind == service_kind.value)
        if not include_inactive:
            stmt = stmt.where(ServiceTariff.is_active == True)  # noqa: E712
        stmt = stmt.order_by(
            ServiceTariff.service_kind,
            ServiceTariff.sort_order,
            ServiceTariff.category,
            ServiceTariff.power_range,
            ServiceTariff.id,
        )
        res = await session.execute(stmt)
        tariffs = list(res.scalars().all())
        for tariff in tariffs:
            tariff.rules = sorted(
                [rule for rule in tariff.rules if include_inactive or rule.is_active],
                key=lambda item: (item.sort_order, item.id or 0),
            )
        return tariffs

    @staticmethod
    async def get_tariff_by_id(session: AsyncSession, tariff_id: int) -> ServiceTariff:
        stmt = (
            select(ServiceTariff)
            .where(ServiceTariff.id == tariff_id)
            .options(selectinload(ServiceTariff.rules))
            .execution_options(populate_existing=True)
            .limit(1)
        )
        tariff = (await session.execute(stmt)).scalars().first()
        if not tariff:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tariff not found")
        # Keep rules in sync even when the same session already has a cached tariff instance.
        rules_stmt = (
            select(ServiceTariffRule)
            .where(ServiceTariffRule.tariff_id == tariff_id)
            .order_by(ServiceTariffRule.sort_order, ServiceTariffRule.id)
        )
        tariff.rules = list((await session.execute(rules_stmt)).scalars().all())
        return tariff

    @staticmethod
    async def create_tariff(session: AsyncSession, payload: ManagerTariffCreatePayload) -> ServiceTariff:
        tariff = ServiceTariff(
            service_kind=payload.service_kind.value,
            selector_label=payload.selector_label.strip(),
            estimate_template=payload.estimate_template.strip(),
            category=(payload.category or "").strip(),
            power_range=(payload.power_range or "").strip(),
            base_price=int(payload.base_price or 0),
            included_route_meters=float(payload.included_route_meters or 0),
            is_active=bool(payload.is_active),
            sort_order=int(payload.sort_order or 0),
            comment=(payload.comment or "").strip() or None,
        )
        session.add(tariff)
        await session.commit()
        return await TariffsService.get_tariff_by_id(session, int(tariff.id))

    @staticmethod
    async def update_tariff(
        session: AsyncSession,
        tariff_id: int,
        payload: ManagerTariffUpdatePayload,
    ) -> ServiceTariff:
        tariff = await TariffsService.get_tariff_by_id(session, tariff_id)
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "service_kind" and value is not None:
                setattr(tariff, key, value.value if hasattr(value, "value") else str(value))
                continue
            if key in {"selector_label", "estimate_template", "category", "power_range", "comment"}:
                setattr(tariff, key, (value or "").strip() or (None if key == "comment" else ""))
                continue
            setattr(tariff, key, value)

        session.add(tariff)
        await session.commit()
        return await TariffsService.get_tariff_by_id(session, tariff_id)

    @staticmethod
    async def delete_tariff(session: AsyncSession, tariff_id: int) -> None:
        tariff = await TariffsService.get_tariff_by_id(session, tariff_id)
        await session.delete(tariff)
        await session.commit()

    @staticmethod
    async def list_tariff_rules(
        session: AsyncSession,
        tariff_id: int,
        include_inactive: bool = True,
    ) -> List[ServiceTariffRule]:
        await TariffsService.get_tariff_by_id(session, tariff_id)
        stmt = select(ServiceTariffRule).where(ServiceTariffRule.tariff_id == tariff_id)
        if not include_inactive:
            stmt = stmt.where(ServiceTariffRule.is_active == True)  # noqa: E712
        stmt = stmt.order_by(ServiceTariffRule.sort_order, ServiceTariffRule.id)
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def get_tariff_rule_by_id(session: AsyncSession, tariff_id: int, rule_id: int) -> ServiceTariffRule:
        stmt = (
            select(ServiceTariffRule)
            .where(ServiceTariffRule.id == rule_id)
            .where(ServiceTariffRule.tariff_id == tariff_id)
            .limit(1)
        )
        rule = (await session.execute(stmt)).scalars().first()
        if not rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tariff rule not found")
        return rule

    @staticmethod
    async def create_tariff_rule(
        session: AsyncSession,
        tariff_id: int,
        payload: ManagerTariffRuleCreatePayload,
    ) -> ServiceTariffRule:
        await TariffsService.get_tariff_by_id(session, tariff_id)
        rule = ServiceTariffRule(
            tariff_id=tariff_id,
            rule_type=payload.rule_type.value,
            name=payload.name.strip(),
            line_template=(payload.line_template or "{name}").strip(),
            unit=(payload.unit or "шт").strip(),
            unit_price=float(payload.unit_price or 0),
            is_optional=bool(payload.is_optional),
            is_active=bool(payload.is_active),
            sort_order=int(payload.sort_order or 0),
            service_id=payload.service_id,
        )
        session.add(rule)
        await session.commit()
        return await TariffsService.get_tariff_rule_by_id(session, tariff_id, int(rule.id))

    @staticmethod
    async def update_tariff_rule(
        session: AsyncSession,
        tariff_id: int,
        rule_id: int,
        payload: ManagerTariffRuleUpdatePayload,
    ) -> ServiceTariffRule:
        rule = await TariffsService.get_tariff_rule_by_id(session, tariff_id, rule_id)
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "rule_type" and value is not None:
                setattr(rule, key, value.value if hasattr(value, "value") else str(value))
                continue
            if key in {"name", "line_template", "unit"} and value is not None:
                setattr(rule, key, str(value).strip())
                continue
            setattr(rule, key, value)

        session.add(rule)
        await session.commit()
        return await TariffsService.get_tariff_rule_by_id(session, tariff_id, rule_id)

    @staticmethod
    async def delete_tariff_rule(session: AsyncSession, tariff_id: int, rule_id: int) -> None:
        rule = await TariffsService.get_tariff_rule_by_id(session, tariff_id, rule_id)
        await session.delete(rule)
        await session.commit()
