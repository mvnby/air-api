"""Business logic for install estimates and estimate snapshots (issue #260 v1)."""

import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.service_estimate import ServiceEstimateDAO
from models import Customer, InstallationRate, Service, ServiceEstimate, ServiceEstimateItem
from schemas import (
    ManagerActionMessageResponse,
    ManagerEstimateLineResponse,
    ManagerInstallEstimateCalculatePayload,
    ManagerInstallEstimateResponse,
    ManagerInstallEstimateSavePayload,
    ManagerOrderServiceLinePayload,
    ManagerServiceEstimateOrderLinesMode,
    ManagerServiceEstimateOrderLinesResponse,
    ManagerServiceEstimateListResponse,
    ManagerServiceEstimateResponse,
)


class ServiceEstimateService:
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
    def _round_money(value: float) -> float:
        return round(float(value), 2)

    @staticmethod
    def _format_number(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "0"
        if abs(number - round(number)) < 1e-9:
            return str(int(round(number)))
        formatted = f"{number:.2f}"
        return formatted.rstrip("0").rstrip(".")

    @staticmethod
    def _pluralize_hole(count: int) -> str:
        mod10 = count % 10
        mod100 = count % 100
        if mod10 == 1 and mod100 != 11:
            return "алмазное отверстие"
        if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
            return "алмазных отверстия"
        return "алмазных отверстий"

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
            btu_classes = [int(round(num)) for num in numbers]
            mapped_values = [
                ServiceEstimateService.BTU_TO_KW_MAP[btu]
                for btu in btu_classes
                if btu in ServiceEstimateService.BTU_TO_KW_MAP
            ]
            if mapped_values:
                kw_value = max(mapped_values)

        if kw_value is None:
            return None

        kw_text = ServiceEstimateService._format_number(kw_value).replace(".", ",")
        return f"до {kw_text} кВт"

    @staticmethod
    async def _resolve_tariff(
        session: AsyncSession, payload: ManagerInstallEstimateCalculatePayload
    ) -> InstallationRate:
        if payload.tariff_id is not None:
            tariff = await session.get(InstallationRate, payload.tariff_id)
            if tariff is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tariff #{payload.tariff_id} not found",
                )
            return tariff

        category = (payload.category or "").strip()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either tariff_id or category must be provided",
            )

        target_power_range = (payload.power_range or "").strip()
        if target_power_range:
            stmt = (
                select(InstallationRate)
                .where(InstallationRate.category == category)
                .where(InstallationRate.power_range == target_power_range)
                .limit(1)
            )
            exact_result = await session.execute(stmt)
            exact_tariff = exact_result.scalars().first()
            if exact_tariff is not None:
                return exact_tariff

        fallback_stmt = (
            select(InstallationRate)
            .where(InstallationRate.category == category)
            .order_by(InstallationRate.id)
            .limit(1)
        )
        fallback_result = await session.execute(fallback_stmt)
        fallback_tariff = fallback_result.scalars().first()
        if fallback_tariff is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tariff not found for category='{category}'",
            )
        return fallback_tariff

    @staticmethod
    async def _build_lines(
        session: AsyncSession,
        payload: ManagerInstallEstimateCalculatePayload,
        tariff: InstallationRate,
    ) -> Tuple[List[ManagerEstimateLineResponse], float]:
        lines: List[ManagerEstimateLineResponse] = []
        sort_order = 0
        quantity = float(payload.quantity)

        base_unit_price = float(tariff.base_price or 0)
        base_line_total = base_unit_price * quantity
        lines.append(
            ManagerEstimateLineResponse(
                source_type="base",
                source_id=tariff.id,
                name=f"Базовый монтаж ({tariff.category} {tariff.power_range or 'all'})",
                qty=quantity,
                unit="компл.",
                unit_price=ServiceEstimateService._round_money(base_unit_price),
                line_total=ServiceEstimateService._round_money(base_line_total),
                sort_order=sort_order,
            )
        )
        sort_order += 1

        included_meters = float(tariff.included_pipe_meters or 0)
        extra_pipe_meters = max(float(payload.route_length_m) - included_meters, 0.0)
        extra_pipe_unit_price = float(tariff.extra_pipe_price or 0)
        if extra_pipe_meters > 0 and extra_pipe_unit_price > 0:
            extra_pipe_qty = extra_pipe_meters * quantity
            extra_pipe_total = extra_pipe_qty * extra_pipe_unit_price
            lines.append(
                ManagerEstimateLineResponse(
                    source_type="modifier",
                    source_id=tariff.id,
                    name=f"Доп. трасса свыше {int(included_meters)} м",
                    qty=ServiceEstimateService._round_money(extra_pipe_qty),
                    unit="м",
                    unit_price=ServiceEstimateService._round_money(extra_pipe_unit_price),
                    line_total=ServiceEstimateService._round_money(extra_pipe_total),
                    sort_order=sort_order,
                )
            )
            sort_order += 1

        extra_hole_price = float(payload.extra_hole_price or 0)
        if payload.extra_holes_count > 0 and extra_hole_price > 0:
            extra_holes_qty = float(payload.extra_holes_count) * quantity
            extra_holes_total = extra_holes_qty * extra_hole_price
            lines.append(
                ManagerEstimateLineResponse(
                    source_type="modifier",
                    source_id=None,
                    name="Дополнительные отверстия",
                    qty=ServiceEstimateService._round_money(extra_holes_qty),
                    unit="шт",
                    unit_price=ServiceEstimateService._round_money(extra_hole_price),
                    line_total=ServiceEstimateService._round_money(extra_holes_total),
                    sort_order=sort_order,
                )
            )
            sort_order += 1

        if payload.addons:
            addon_slugs = [a.slug for a in payload.addons]
            addon_stmt = (
                select(Service)
                .where(Service.slug.in_(addon_slugs))
                .where(Service.is_active == True)  # noqa: E712
            )
            addon_result = await session.execute(addon_stmt)
            addon_services = {svc.slug: svc for svc in addon_result.scalars().all()}

            missing_slugs = sorted({slug for slug in addon_slugs if slug not in addon_services})
            if missing_slugs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown add-on slugs: {', '.join(missing_slugs)}",
                )

            for addon in payload.addons:
                service = addon_services[addon.slug]
                addon_qty = float(addon.qty) * quantity
                addon_price = float(service.base_price or 0)
                addon_total = addon_qty * addon_price
                lines.append(
                    ManagerEstimateLineResponse(
                        source_type="addon",
                        source_id=service.id,
                        name=service.title,
                        qty=ServiceEstimateService._round_money(addon_qty),
                        unit="шт",
                        unit_price=ServiceEstimateService._round_money(addon_price),
                        line_total=ServiceEstimateService._round_money(addon_total),
                        sort_order=sort_order,
                    )
                )
                sort_order += 1

        return lines, ServiceEstimateService._round_money(extra_pipe_meters)

    @staticmethod
    async def calculate_install_estimate(
        session: AsyncSession, payload: ManagerInstallEstimateCalculatePayload
    ) -> ManagerInstallEstimateResponse:
        tariff = await ServiceEstimateService._resolve_tariff(session, payload)
        lines, extra_pipe_meters = await ServiceEstimateService._build_lines(session, payload, tariff)

        subtotal = ServiceEstimateService._round_money(sum(float(line.line_total) for line in lines))
        discount_amount = ServiceEstimateService._round_money(min(float(payload.discount_amount), subtotal))
        total = ServiceEstimateService._round_money(max(subtotal - discount_amount, 0.0))

        return ManagerInstallEstimateResponse(
            tariff_id=int(tariff.id),
            category=tariff.category,
            power_range=tariff.power_range,
            currency="BYN",
            route_length_m=float(payload.route_length_m),
            included_pipe_meters=int(tariff.included_pipe_meters or 0),
            extra_pipe_meters=extra_pipe_meters,
            quantity=int(payload.quantity),
            lines=lines,
            subtotal=subtotal,
            discount_amount=discount_amount,
            total=total,
        )

    @staticmethod
    def _map_estimate_to_response(estimate: ServiceEstimate) -> ManagerServiceEstimateResponse:
        line_items = sorted(list(estimate.items or []), key=lambda item: item.sort_order)
        lines = [
            ManagerEstimateLineResponse(
                source_type=item.source_type,
                source_id=item.source_id,
                name=item.name,
                qty=float(item.qty),
                unit=item.unit,
                unit_price=float(item.unit_price),
                line_total=float(item.line_total),
                sort_order=item.sort_order,
            )
            for item in line_items
        ]
        return ManagerServiceEstimateResponse(
            id=int(estimate.id),
            customer_id=estimate.customer_id,
            title=estimate.title,
            comment=estimate.comment,
            service_kind=estimate.service_kind,
            currency=estimate.currency,
            subtotal=float(estimate.subtotal),
            discount_amount=float(estimate.discount_amount),
            total=float(estimate.total),
            status=estimate.status,
            created_by=estimate.created_by,
            created_at=estimate.created_at,
            lines=lines,
            calculation_payload=estimate.calculation_payload,
        )

    @staticmethod
    async def create_install_estimate(
        session: AsyncSession,
        payload: ManagerInstallEstimateSavePayload,
        created_by: Optional[str],
    ) -> ManagerServiceEstimateResponse:
        if payload.customer_id is not None:
            customer = await session.get(Customer, payload.customer_id)
            if customer is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Customer #{payload.customer_id} not found",
                )

        calculation = await ServiceEstimateService.calculate_install_estimate(session, payload)
        default_title = (
            f"Смета монтажа: {calculation.category}"
            + (f" / {calculation.power_range}" if calculation.power_range else "")
        )

        estimate = ServiceEstimate(
            customer_id=payload.customer_id,
            title=(payload.title or default_title).strip(),
            comment=payload.comment,
            service_kind="install",
            currency=calculation.currency,
            subtotal=calculation.subtotal,
            discount_amount=calculation.discount_amount,
            total=calculation.total,
            calculation_payload=payload.model_dump(mode="json"),
            status=(payload.status or "draft").strip() or "draft",
            created_by=(created_by or "").strip() or None,
        )
        items = [
            ServiceEstimateItem(
                source_type=line.source_type,
                source_id=line.source_id,
                name=line.name,
                qty=line.qty,
                unit=line.unit,
                unit_price=line.unit_price,
                line_total=line.line_total,
                sort_order=line.sort_order,
            )
            for line in calculation.lines
        ]

        saved = await ServiceEstimateDAO.create(session, estimate, items)
        return ServiceEstimateService._map_estimate_to_response(saved)

    @staticmethod
    async def get_estimate_by_id(
        session: AsyncSession, estimate_id: int
    ) -> ManagerServiceEstimateResponse:
        estimate = await ServiceEstimateDAO.get_by_id(session, estimate_id)
        if estimate is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Estimate #{estimate_id} not found",
            )
        return ServiceEstimateService._map_estimate_to_response(estimate)

    @staticmethod
    async def list_estimates(
        session: AsyncSession,
        page: int = 1,
        limit: int = 20,
        customer_id: Optional[int] = None,
    ) -> ManagerServiceEstimateListResponse:
        safe_page = max(1, page)
        safe_limit = max(1, min(limit, 100))
        items, total = await ServiceEstimateDAO.list(
            session=session,
            page=safe_page,
            limit=safe_limit,
            customer_id=customer_id,
        )
        return ManagerServiceEstimateListResponse(
            items=[ServiceEstimateService._map_estimate_to_response(item) for item in items],
            total=total,
            page=safe_page,
            limit=safe_limit,
        )

    @staticmethod
    def _build_collapsed_title(estimate: ServiceEstimate) -> str:
        payload: Dict[str, Any] = dict(estimate.calculation_payload or {})
        route_length = payload.get("route_length_m")
        extra_holes = int(payload.get("extra_holes_count") or 0)
        quantity = int(payload.get("quantity") or 1)

        addon_names = [
            item.name
            for item in sorted(list(estimate.items or []), key=lambda i: i.sort_order)
            if item.source_type == "addon"
        ]

        parts: List[str] = ["включая расходные материалы"]

        power_label = ServiceEstimateService._extract_power_label(
            str(payload.get("power_range") or "")
        )
        head = "Стандартный монтаж кондиционера"
        if power_label:
            head = f"{head} {power_label}"

        if extra_holes > 0:
            parts.append(f"{extra_holes} {ServiceEstimateService._pluralize_hole(extra_holes)}")
        if route_length is not None:
            parts.append(f"трасса {ServiceEstimateService._format_number(route_length)} м")
        if addon_names:
            parts.append(f"доп. работы: {', '.join(addon_names)}")
        if quantity > 1:
            parts.append(f"количество комплектов: {quantity}")

        return f"{head}, " + ", ".join(parts)

    @staticmethod
    def _map_item_to_detailed_service_line(item: ServiceEstimateItem) -> ManagerOrderServiceLinePayload:
        qty_label = ServiceEstimateService._format_number(item.qty)
        unit_label = (item.unit or "").strip()
        title = item.name
        if unit_label and (item.qty != 1 or unit_label not in {"шт", "компл."}):
            title = f"{item.name} ({qty_label} {unit_label})"

        # Order service rows currently support integer quantity only.
        # To preserve exact estimate totals (including fractional meters),
        # each estimate item is materialized as one row with full line_total as price.
        return ManagerOrderServiceLinePayload(
            link_id=None,
            service_id=item.source_id if item.source_type == "addon" else None,
            title=title,
            quantity=1,
            price=max(0, int(round(float(item.line_total or 0.0)))),
            cost=None,
        )

    @staticmethod
    async def get_estimate_order_lines(
        session: AsyncSession,
        estimate_id: int,
        mode: ManagerServiceEstimateOrderLinesMode = ManagerServiceEstimateOrderLinesMode.detailed,
    ) -> ManagerServiceEstimateOrderLinesResponse:
        estimate = await ServiceEstimateDAO.get_by_id(session, estimate_id)
        if estimate is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Estimate #{estimate_id} not found",
            )

        sorted_items = sorted(list(estimate.items or []), key=lambda item: item.sort_order)
        if mode == ManagerServiceEstimateOrderLinesMode.collapsed:
            collapsed_title = ServiceEstimateService._build_collapsed_title(estimate)
            services = [
                ManagerOrderServiceLinePayload(
                    link_id=None,
                    service_id=None,
                    title=collapsed_title,
                    quantity=1,
                    price=max(0, int(round(float(estimate.total or 0.0)))),
                    cost=None,
                )
            ]
            return ManagerServiceEstimateOrderLinesResponse(
                estimate_id=int(estimate.id),
                mode=mode,
                title=collapsed_title,
                services=services,
            )

        services = [ServiceEstimateService._map_item_to_detailed_service_line(item) for item in sorted_items]
        return ManagerServiceEstimateOrderLinesResponse(
            estimate_id=int(estimate.id),
            mode=mode,
            title=estimate.title,
            services=services,
        )

    @staticmethod
    async def delete_estimate(session: AsyncSession, estimate_id: int) -> ManagerActionMessageResponse:
        deleted = await ServiceEstimateDAO.delete_by_id(session=session, estimate_id=estimate_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Estimate #{estimate_id} not found",
            )
        return ManagerActionMessageResponse(message=f"Estimate #{estimate_id} deleted")
