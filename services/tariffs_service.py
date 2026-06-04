import logging
import re
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import ServiceTariff, ServiceTariffRule
from schemas import (
    ManagerTariffCreatePayload,
    ManagerQuickTariffResponse,
    ManagerTariffRuleCreatePayload,
    ManagerTariffRuleUpdatePayload,
    ManagerTariffServiceKind,
    ManagerTariffUpdatePayload,
)

logger = logging.getLogger(__name__)


class TariffsService:
    ROUTE_AWARE_SERVICE_KINDS = {
        ManagerTariffServiceKind.installation.value,
        ManagerTariffServiceKind.pre_install.value,
    }

    BTU_TO_KW_MAP = {
        7: 2.1,
        9: 2.6,
        12: 3.5,
        18: 5.3,
        24: 7.0,
        30: 8.8,
        36: 10.5,
        42: 12.3,
        48: 14.0,
        60: 17.6,
    }

    @staticmethod
    def _format_number(value: float) -> str:
        number = float(value)
        if abs(number - round(number)) < 1e-9:
            return str(int(round(number)))
        return f"{number:.2f}".rstrip("0").rstrip(".").replace(".", ",")

    @staticmethod
    def supports_route_meters(service_kind: ManagerTariffServiceKind | str | None) -> bool:
        kind_value = service_kind.value if hasattr(service_kind, "value") else str(service_kind or "")
        return kind_value in TariffsService.ROUTE_AWARE_SERVICE_KINDS

    @staticmethod
    def _extract_power_label(power_range: str) -> Optional[str]:
        raw = (power_range or "").strip()
        if not raw:
            return None
        normalized = raw.replace(",", ".").lower()
        numbers = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", normalized)]
        if not numbers:
            return None

        kw_value: Optional[float] = None
        if "квт" in normalized or "kw" in normalized:
            kw_value = max(numbers)
        else:
            mapped = [
                TariffsService.BTU_TO_KW_MAP[int(round(number))]
                for number in numbers
                if int(round(number)) in TariffsService.BTU_TO_KW_MAP
            ]
            if mapped:
                kw_value = max(mapped)

        if kw_value is None:
            return None
        return f"до {TariffsService._format_number(kw_value)} кВт"

    @staticmethod
    def build_quick_add_title(tariff: ServiceTariff) -> str:
        selector = (tariff.selector_label or "").strip()
        template = (tariff.estimate_template or "").strip()
        base = selector or template or "Услуга"

        title = base.rstrip(" .,")
        normalized_title = title.lower()
        power_label = TariffsService._extract_power_label(tariff.power_range or "")
        if power_label and "квт" not in normalized_title and "kw" not in normalized_title and "мощност" not in normalized_title:
            title = f"{title}, мощностью {power_label}"

        included_route = float(tariff.included_route_meters or 0)
        if TariffsService.supports_route_meters(tariff.service_kind) and included_route > 0 and "трасс" not in title.lower():
            title = f"{title}, включая трассу длиной до {TariffsService._format_number(included_route)} м"
        return title

    @staticmethod
    def _map_quick_tariff(tariff: ServiceTariff) -> ManagerQuickTariffResponse:
        try:
            service_kind = ManagerTariffServiceKind(str(tariff.service_kind or "installation"))
        except ValueError:
            service_kind = ManagerTariffServiceKind.installation
        return ManagerQuickTariffResponse(
            tariff_id=int(tariff.id),
            service_kind=service_kind,
            title=TariffsService.build_quick_add_title(tariff),
            price=int(tariff.base_price or 0),
            category=tariff.category or "",
            power_range=tariff.power_range or "",
            included_route_meters=float(tariff.included_route_meters or 0),
        )

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
    async def list_quick_add_tariffs(
        session: AsyncSession,
        service_kind: Optional[ManagerTariffServiceKind] = None,
        q: str = "",
        limit: int = 10,
    ) -> List[ManagerQuickTariffResponse]:
        stmt = select(ServiceTariff).where(ServiceTariff.is_active == True)  # noqa: E712
        if service_kind is not None:
            kind_value = service_kind.value if hasattr(service_kind, "value") else str(service_kind)
            stmt = stmt.where(ServiceTariff.service_kind == kind_value)
        query = (q or "").strip()
        relevance_order = None
        if query:
            pattern = f"%{query}%"
            starts_pattern = f"{query.lower()}%"
            stmt = stmt.where(
                or_(
                    ServiceTariff.selector_label.ilike(pattern),
                    ServiceTariff.estimate_template.ilike(pattern),
                    ServiceTariff.category.ilike(pattern),
                    ServiceTariff.power_range.ilike(pattern),
                    ServiceTariff.comment.ilike(pattern),
                )
            )
            relevance_order = case(
                (func.lower(ServiceTariff.selector_label).like(starts_pattern), 0),
                (func.lower(ServiceTariff.estimate_template).like(starts_pattern), 1),
                else_=2,
            )
        order_by = [
            ServiceTariff.service_kind,
            ServiceTariff.sort_order,
            ServiceTariff.category,
            ServiceTariff.power_range,
            ServiceTariff.id,
        ]
        if relevance_order is not None:
            order_by.insert(0, relevance_order)
        stmt = stmt.order_by(*order_by).limit(max(1, min(int(limit or 10), 50)))
        result = await session.execute(stmt)
        return [TariffsService._map_quick_tariff(tariff) for tariff in result.scalars().all()]

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
        included_route_meters = (
            float(payload.included_route_meters or 0)
            if TariffsService.supports_route_meters(payload.service_kind)
            else 0.0
        )
        tariff = ServiceTariff(
            service_kind=payload.service_kind.value,
            selector_label=payload.selector_label.strip(),
            estimate_template=payload.estimate_template.strip(),
            category=(payload.category or "").strip(),
            power_range=(payload.power_range or "").strip(),
            base_price=int(payload.base_price or 0),
            included_route_meters=included_route_meters,
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
        next_service_kind = update_data.get("service_kind", tariff.service_kind)
        next_service_kind_value = (
            next_service_kind.value if hasattr(next_service_kind, "value") else str(next_service_kind or "installation")
        )
        for key, value in update_data.items():
            if key == "service_kind" and value is not None:
                setattr(tariff, key, value.value if hasattr(value, "value") else str(value))
                continue
            if key in {"selector_label", "estimate_template", "category", "power_range", "comment"}:
                setattr(tariff, key, (value or "").strip() or (None if key == "comment" else ""))
                continue
            setattr(tariff, key, value)
        if not TariffsService.supports_route_meters(next_service_kind_value):
            tariff.included_route_meters = 0.0

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
    async def list_favorite_tariff_rules(
        session: AsyncSession,
        service_kind: ManagerTariffServiceKind,
        include_inactive: bool = False,
        exclude_tariff_id: Optional[int] = None,
    ) -> List[ServiceTariffRule]:
        stmt = (
            select(ServiceTariffRule)
            .join(ServiceTariff)
            .where(ServiceTariffRule.is_favorite == True)  # noqa: E712
            .where(ServiceTariff.service_kind == service_kind.value)
        )
        if not include_inactive:
            stmt = stmt.where(ServiceTariffRule.is_active == True)  # noqa: E712
            stmt = stmt.where(ServiceTariff.is_active == True)  # noqa: E712
        if exclude_tariff_id is not None:
            stmt = stmt.where(ServiceTariffRule.tariff_id != exclude_tariff_id)
        stmt = stmt.order_by(
            ServiceTariffRule.name,
            ServiceTariffRule.sort_order,
            ServiceTariffRule.id,
        )
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
        rule_type = payload.rule_type.value
        name = payload.name.strip()
        line_template = (payload.line_template or "{name}").strip()
        unit = (payload.unit or "шт").strip()
        unit_price = float(payload.unit_price or 0)
        service_id = payload.service_id

        duplicate_stmt = (
            select(ServiceTariffRule)
            .where(ServiceTariffRule.tariff_id == tariff_id)
            .where(ServiceTariffRule.rule_type == rule_type)
            .where(ServiceTariffRule.name == name)
            .where(ServiceTariffRule.line_template == line_template)
            .where(ServiceTariffRule.unit == unit)
            .where(ServiceTariffRule.unit_price == unit_price)
            .where(ServiceTariffRule.is_optional == bool(payload.is_optional))
            .limit(1)
        )
        if service_id is None:
            duplicate_stmt = duplicate_stmt.where(ServiceTariffRule.service_id.is_(None))
        else:
            duplicate_stmt = duplicate_stmt.where(ServiceTariffRule.service_id == service_id)

        existing = (await session.execute(duplicate_stmt)).scalars().first()
        if existing:
            if payload.is_favorite and not existing.is_favorite:
                existing.is_favorite = True
                session.add(existing)
                await session.commit()
                return await TariffsService.get_tariff_rule_by_id(session, tariff_id, int(existing.id))
            return existing

        rule = ServiceTariffRule(
            tariff_id=tariff_id,
            rule_type=rule_type,
            name=name,
            line_template=line_template,
            unit=unit,
            unit_price=unit_price,
            is_optional=bool(payload.is_optional),
            is_favorite=bool(payload.is_favorite),
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
