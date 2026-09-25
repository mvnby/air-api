"""Business logic for service estimates based on directional service tariffs."""

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.service_estimate import ServiceEstimateDAO
from models import Customer, ServiceEstimate, ServiceEstimateItem, ServiceTariff, ServiceTariffRule
from models.tenancy import TenantScope
from schemas import (
    ManagerActionMessageResponse,
    ManagerEstimateLineResponse,
    ManagerInstallEstimateCalculatePayload,
    ManagerInstallEstimateResponse,
    ManagerInstallEstimateSavePayload,
    ManagerOrderServiceLinePayload,
    ManagerServiceDescriptionMode,
    ManagerServiceEstimateOrderLinesMode,
    ManagerServiceEstimateOrderLinesResponse,
    ManagerServiceEstimateListResponse,
    ManagerServiceEstimateResponse,
    ManagerTariffBriefResponse,
    ManagerTariffRuleType,
    ManagerTariffServiceKind,
)
from services.tariffs_service import TariffsService
from services.cooling_capacity import BTU_TO_KW_MAP
from services.service_catalog_scope import service_catalog_write_tenant_id
from services.service_estimate_money import allocate_discount, decimal_value, money, snapshot_money, writable_service_money
from services.legacy_installation_estimate_policy import LegacyInstallationEstimatePolicy


class ServiceEstimateService:
    @staticmethod
    def _round_money(value: float) -> float:
        return float(money(value))

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
                BTU_TO_KW_MAP[btu]
                for btu in btu_classes
                if btu in BTU_TO_KW_MAP
            ]
            if mapped_values:
                kw_value = max(mapped_values)

        if kw_value is None:
            return None
        kw_text = ServiceEstimateService._format_number(kw_value).replace(".", ",")
        return f"до {kw_text} кВт"

    @staticmethod
    def _render_line_template(
        line_template: str,
        *,
        name: str,
        qty: float,
        unit: str,
        unit_price: float,
        route_length_m: float,
        included_route_meters: float,
        extra_route_meters: float,
        extra_holes_count: int,
        quantity: int,
    ) -> str:
        safe_context = {
            "name": name,
            "qty": ServiceEstimateService._format_number(qty),
            "unit": unit,
            "unit_price": ServiceEstimateService._format_number(unit_price),
            "route_length_m": ServiceEstimateService._format_number(route_length_m),
            "included_route_meters": ServiceEstimateService._format_number(included_route_meters),
            "extra_route_meters": ServiceEstimateService._format_number(extra_route_meters),
            "extra_holes_count": str(int(extra_holes_count)),
            "quantity": str(int(quantity)),
        }
        try:
            rendered = str(line_template or "").format(**safe_context).strip()
            return rendered or name
        except Exception:
            return name

    @staticmethod
    def _map_tariff_brief(tariff: ServiceTariff) -> ManagerTariffBriefResponse:
        try:
            service_kind = ManagerTariffServiceKind(str(tariff.service_kind or "installation"))
        except ValueError:
            service_kind = ManagerTariffServiceKind.installation
        return ManagerTariffBriefResponse(
            id=int(tariff.id),
            service_kind=service_kind,
            short_name=tariff.effective_short_name,
            full_description=(tariff.full_description or "").strip() or None,
            selector_label=tariff.selector_label,
            estimate_template=tariff.estimate_template,
            category=tariff.category,
            power_range=tariff.power_range,
            base_price=int(tariff.base_price or 0),
            included_route_meters=float(tariff.included_route_meters or 0),
        )

    @staticmethod
    async def _resolve_tariff(
        session: AsyncSession,
        payload: ManagerInstallEstimateCalculatePayload,
        tenant_scope: TenantScope | None = None,
    ) -> ServiceTariff:
        return await TariffsService.get_tariff_by_id(
            session,
            payload.tariff_id,
            tenant_scope,
        )

    @staticmethod
    def _rule_inputs_map(payload: ManagerInstallEstimateCalculatePayload) -> Dict[int, Decimal]:
        result: Dict[int, Decimal] = {}
        for item in payload.rule_inputs:
            result[int(item.rule_id)] = decimal_value(item.qty)
        return result

    @staticmethod
    def _build_base_line(tariff: ServiceTariff, quantity: int, sort_order: int) -> ManagerEstimateLineResponse:
        qty = Decimal(quantity)
        unit_price = decimal_value(tariff.base_price)
        return ManagerEstimateLineResponse(
            source_type="base",
            source_id=int(tariff.id),
            rule_id=None,
            rule_type=None,
            service_id=None,
            name=tariff.effective_short_name or "Базовая услуга",
            short_name=tariff.effective_short_name or "Базовая услуга",
            full_description=tariff.effective_full_description or None,
            qty=float(qty),
            unit="компл.",
            unit_price=float(unit_price),
            line_total=ServiceEstimateService._round_money(qty * unit_price),
            sort_order=sort_order,
        )

    @staticmethod
    def _rule_default_qty(rule: ServiceTariffRule) -> float:
        if rule.rule_type == ManagerTariffRuleType.fixed_once.value:
            return 0.0 if rule.is_optional else 1.0
        if rule.rule_type == ManagerTariffRuleType.per_unit_manual.value:
            return 0.0 if rule.is_optional else 1.0
        return 0.0

    @staticmethod
    def _build_rule_line(
        rule: ServiceTariffRule,
        *,
        tariff: ServiceTariff,
        payload: ManagerInstallEstimateCalculatePayload,
        quantity: int,
        rule_input_qty: Optional[Decimal],
        sort_order: int,
    ) -> Optional[ManagerEstimateLineResponse]:
        route_length = decimal_value(payload.route_length_m)
        included_route = decimal_value(tariff.included_route_meters)
        extra_route = max(route_length - included_route, Decimal("0"))
        extra_holes = int(payload.extra_holes_count or 0)
        unit_price = decimal_value(rule.unit_price)

        qty = Decimal("0")
        if rule.rule_type == ManagerTariffRuleType.per_meter_over_included.value:
            qty = extra_route * quantity
        elif rule.rule_type == ManagerTariffRuleType.per_hole_manual.value:
            qty = Decimal(extra_holes) * quantity
        elif rule.rule_type == ManagerTariffRuleType.per_unit_manual.value:
            base_qty = rule_input_qty if rule_input_qty is not None else ServiceEstimateService._rule_default_qty(rule)
            qty = decimal_value(base_qty) * quantity
        elif rule.rule_type == ManagerTariffRuleType.fixed_once.value:
            qty = decimal_value(rule_input_qty if rule_input_qty is not None else ServiceEstimateService._rule_default_qty(rule))
        else:
            return None

        if qty <= 0:
            return None

        line_total = qty * unit_price
        name = ServiceEstimateService._render_line_template(
            rule.line_template,
            name=rule.name,
            qty=float(qty),
            unit=rule.unit,
            unit_price=float(unit_price),
            route_length_m=route_length,
            included_route_meters=included_route,
            extra_route_meters=extra_route,
            extra_holes_count=extra_holes,
            quantity=quantity,
        )
        return ManagerEstimateLineResponse(
            source_type="rule",
            source_id=int(rule.id),
            rule_id=int(rule.id),
            rule_type=ManagerTariffRuleType(rule.rule_type),
            service_id=rule.service_id,
            name=name,
            short_name=name,
            full_description=name,
            qty=qty,
            unit=rule.unit,
            unit_price=unit_price,
            line_total=ServiceEstimateService._round_money(line_total),
            sort_order=sort_order,
        )

    @staticmethod
    async def _build_lines(
        payload: ManagerInstallEstimateCalculatePayload,
        tariff: ServiceTariff,
    ) -> List[ManagerEstimateLineResponse]:
        lines: List[ManagerEstimateLineResponse] = []
        sort_order = 0
        quantity = int(payload.quantity)

        lines.append(ServiceEstimateService._build_base_line(tariff, quantity, sort_order))
        sort_order += 1

        rule_inputs = ServiceEstimateService._rule_inputs_map(payload)
        sorted_rules = sorted(
            [rule for rule in list(tariff.rules or []) if rule.is_active and rule.component_code != "discount.equipment_bundle"],
            key=lambda item: (item.sort_order, item.id or 0),
        )
        for rule in sorted_rules:
            rule_line = ServiceEstimateService._build_rule_line(
                rule,
                tariff=tariff,
                payload=payload,
                quantity=quantity,
                rule_input_qty=rule_inputs.get(int(rule.id)),
                sort_order=sort_order,
            )
            if rule_line is None:
                continue
            lines.append(rule_line)
            sort_order += 1
        return lines

    @staticmethod
    async def calculate_install_estimate(
        session: AsyncSession,
        payload: ManagerInstallEstimateCalculatePayload,
        tenant_scope: TenantScope | None = None,
    ) -> ManagerInstallEstimateResponse:
        tariff = await ServiceEstimateService._resolve_tariff(
            session, payload, tenant_scope
        )
        await LegacyInstallationEstimatePolicy.require_available(
            session, tenant_scope, tariff,
        )
        lines = await ServiceEstimateService._build_lines(payload, tariff)
        subtotal_money = sum((money(line.line_total) for line in lines), Decimal("0.00"))
        discount_money = min(money(payload.discount_amount), subtotal_money)
        subtotal = float(subtotal_money)
        discount_amount = float(discount_money)
        total = float(subtotal_money - discount_money)
        rule_lines = [line for line in lines if line.source_type == "rule"]

        return ManagerInstallEstimateResponse(
            tariff=ServiceEstimateService._map_tariff_brief(tariff),
            currency="BYN",
            route_length_m=float(payload.route_length_m),
            quantity=int(payload.quantity),
            lines=lines,
            rule_lines=rule_lines,
            subtotal=subtotal,
            discount_amount=discount_amount,
            total=total,
        )

    @staticmethod
    def _map_estimate_to_response(estimate: ServiceEstimate) -> ManagerServiceEstimateResponse:
        line_items = sorted(list(estimate.items or []), key=lambda item: item.sort_order)
        rules_by_id: Dict[int, ServiceTariffRule] = {}
        if estimate.tariff and estimate.tariff.rules:
            rules_by_id = {int(rule.id): rule for rule in estimate.tariff.rules if rule.id is not None}

        lines: List[ManagerEstimateLineResponse] = []
        for item in line_items:
            rule_id: Optional[int] = None
            rule_type: Optional[ManagerTariffRuleType] = None
            if item.source_type == "rule" and item.source_id is not None:
                rule_id = int(item.source_id)
                mapped_rule = rules_by_id.get(rule_id)
                if mapped_rule and mapped_rule.rule_type:
                    rule_type = ManagerTariffRuleType(mapped_rule.rule_type)
            lines.append(
                ManagerEstimateLineResponse(
                    source_type=item.source_type,
                    source_id=item.source_id,
                    rule_id=rule_id,
                    rule_type=rule_type,
                    service_id=item.service_id,
                    name=item.name,
                    short_name=(item.short_name or item.name or "").strip() or item.name,
                    full_description=(item.full_description or "").strip() or None,
                    qty=float(item.qty),
                    unit=item.unit,
                    unit_price=float(item.unit_price),
                    line_total=float(item.line_total),
                    sort_order=item.sort_order,
                )
            )

        return ManagerServiceEstimateResponse(
            id=int(estimate.id),
            customer_id=estimate.customer_id,
            tariff=ServiceEstimateService._map_tariff_brief(estimate.tariff) if estimate.tariff else None,
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
        tenant_scope: TenantScope | None = None,
    ) -> ManagerServiceEstimateResponse:
        tariff = await ServiceEstimateService._resolve_tariff(
            session, payload, tenant_scope,
        )
        await LegacyInstallationEstimatePolicy.require_available(
            session, tenant_scope, tariff, serialize_write=True,
        )
        if payload.customer_id is not None:
            customer_stmt = select(Customer).where(
                Customer.id == payload.customer_id
            )
            if tenant_scope is not None:
                customer_stmt = customer_stmt.where(
                    Customer.tenant_id == tenant_scope.tenant_id
                )
            customer = (await session.execute(customer_stmt)).scalars().first()
            if customer is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Customer #{payload.customer_id} not found",
                )

        calculation = await ServiceEstimateService.calculate_install_estimate(
            session, payload, tenant_scope
        )
        default_title = f"Смета: {calculation.tariff.short_name}"
        estimate = ServiceEstimate(
            tenant_id=(
                None
                if tenant_scope is None
                else service_catalog_write_tenant_id(tenant_scope)
            ),
            customer_id=payload.customer_id,
            tariff_id=calculation.tariff.id,
            title=(payload.title or default_title).strip(),
            comment=payload.comment,
            service_kind=calculation.tariff.service_kind.value,
            currency=calculation.currency,
            subtotal=money(calculation.subtotal),
            discount_amount=money(calculation.discount_amount),
            total=money(calculation.total),
            calculation_payload=payload.model_dump(mode="json"),
            status=(payload.status or "draft").strip() or "draft",
            created_by=(created_by or "").strip() or None,
        )
        items = [
            ServiceEstimateItem(
                source_type=line.source_type,
                source_id=line.source_id,
                service_id=line.service_id,
                name=line.name,
                short_name=line.short_name or line.name,
                full_description=line.full_description,
                qty=line.qty,
                unit=line.unit,
                unit_price=line.unit_price,
                line_total=money(line.line_total),
                sort_order=line.sort_order,
            )
            for line in calculation.lines
        ]

        saved = await ServiceEstimateDAO.create(session, estimate, items)
        return ServiceEstimateService._map_estimate_to_response(saved)

    @staticmethod
    async def get_estimate_by_id(
        session: AsyncSession,
        estimate_id: int,
        tenant_scope: TenantScope | None = None,
    ) -> ManagerServiceEstimateResponse:
        estimate = await ServiceEstimateDAO.get_by_id(
            session, estimate_id, tenant_scope
        )
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
        tenant_scope: TenantScope | None = None,
    ) -> ManagerServiceEstimateListResponse:
        safe_page = max(1, page)
        safe_limit = max(1, min(limit, 100))
        items, total = await ServiceEstimateDAO.list(
            session=session,
            page=safe_page,
            limit=safe_limit,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        return ManagerServiceEstimateListResponse(
            items=[ServiceEstimateService._map_estimate_to_response(item) for item in items],
            total=total,
            page=safe_page,
            limit=safe_limit,
        )

    @staticmethod
    def _item_description(
        item: ServiceEstimateItem,
        description_mode: ManagerServiceDescriptionMode,
    ) -> str:
        short_name = (item.short_name or item.name or "").strip()
        if description_mode == ManagerServiceDescriptionMode.full:
            return (item.full_description or "").strip() or short_name
        return short_name

    @staticmethod
    def _build_collapsed_title_from_new_model(
        estimate: ServiceEstimate,
        description_mode: ManagerServiceDescriptionMode,
    ) -> str:
        sorted_items = sorted(list(estimate.items or []), key=lambda item: item.sort_order)
        base_item = next((item for item in sorted_items if item.source_type == "base"), None)
        if base_item:
            head = ServiceEstimateService._item_description(base_item, description_mode)
        elif estimate.tariff:
            head = (
                estimate.tariff.effective_full_description
                if description_mode == ManagerServiceDescriptionMode.full
                else estimate.tariff.effective_short_name
            )
        else:
            head = estimate.title
        head = (head or "").strip() or estimate.title
        rule_parts = [
            (item.name or "").strip()
            for item in sorted_items
            if item.source_type == "rule" and (item.name or "").strip()
        ]
        if not rule_parts:
            return head
        return f"{head}; " + "; ".join(rule_parts)

    @staticmethod
    def _build_legacy_collapsed_title(estimate: ServiceEstimate) -> str:
        payload: Dict[str, Any] = dict(estimate.calculation_payload or {})
        route_length = payload.get("route_length_m")
        extra_holes = int(payload.get("extra_holes_count") or 0)
        quantity = int(payload.get("quantity") or 1)

        parts: List[str] = ["включая расходные материалы"]
        power_label = ServiceEstimateService._extract_power_label(str(payload.get("power_range") or ""))
        head = "Стандартный монтаж кондиционера"
        if power_label:
            head = f"{head} {power_label}"

        if extra_holes > 0:
            parts.append(f"{extra_holes} {ServiceEstimateService._pluralize_hole(extra_holes)}")
        if route_length is not None:
            parts.append(f"трасса {ServiceEstimateService._format_number(route_length)} м")
        if quantity > 1:
            parts.append(f"количество комплектов: {quantity}")
        return f"{head}, " + ", ".join(parts)

    @staticmethod
    def _map_item_to_detailed_service_line(
        item: ServiceEstimateItem,
        description_mode: ManagerServiceDescriptionMode,
        net_total: Decimal,
    ) -> ManagerOrderServiceLinePayload:
        qty_label = ServiceEstimateService._format_number(item.qty)
        unit_label = (item.unit or "").strip()
        title = ServiceEstimateService._item_description(item, description_mode)
        if unit_label and (item.qty != 1 or unit_label not in {"шт", "компл."}):
            title = f"{title} ({qty_label} {unit_label})"

        return ManagerOrderServiceLinePayload(
            link_id=None,
            service_id=item.service_id,
            title=title,
            quantity=1,
            price=net_total,
            cost=None,
        )

    @staticmethod
    async def get_estimate_order_lines(
        session: AsyncSession,
        estimate_id: int,
        mode: ManagerServiceEstimateOrderLinesMode = ManagerServiceEstimateOrderLinesMode.detailed,
        description_mode: ManagerServiceDescriptionMode = ManagerServiceDescriptionMode.short,
        tenant_scope: TenantScope | None = None,
    ) -> ManagerServiceEstimateOrderLinesResponse:
        estimate = await ServiceEstimateDAO.get_by_id(
            session, estimate_id, tenant_scope
        )
        if estimate is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Estimate #{estimate_id} not found",
            )

        sorted_items = sorted(list(estimate.items or []), key=lambda item: item.sort_order)
        try:
            gross = [snapshot_money(item.line_total) for item in sorted_items]
            subtotal = snapshot_money(estimate.subtotal)
            discount = snapshot_money(estimate.discount_amount)
            total = snapshot_money(estimate.total)
            if sum(gross, Decimal("0.00")) != subtotal or subtotal - discount != total:
                raise ValueError("Saved estimate totals do not reconcile")
            net = allocate_discount(gross, discount)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Сохранённая смета #{estimate_id} содержит несовместимые суммы: {exc}",
            ) from exc
        exported = [total] if mode == ManagerServiceEstimateOrderLinesMode.collapsed else net
        try:
            for amount in exported:
                writable_service_money(amount)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        if mode == ManagerServiceEstimateOrderLinesMode.collapsed:
            if estimate.tariff_id:
                collapsed_title = ServiceEstimateService._build_collapsed_title_from_new_model(
                    estimate,
                    description_mode,
                )
            else:
                collapsed_title = ServiceEstimateService._build_legacy_collapsed_title(estimate)

            services = [
                ManagerOrderServiceLinePayload(
                    link_id=None,
                    service_id=None,
                    title=collapsed_title,
                    quantity=1,
                    price=total,
                    cost=None,
                )
            ]
            return ManagerServiceEstimateOrderLinesResponse(
                estimate_id=int(estimate.id),
                mode=mode,
                description_mode=description_mode,
                title=collapsed_title,
                services=services,
            )

        services = [
            ServiceEstimateService._map_item_to_detailed_service_line(item, description_mode, net_total)
            for item, net_total in zip(sorted_items, net)
        ]
        return ManagerServiceEstimateOrderLinesResponse(
            estimate_id=int(estimate.id),
            mode=mode,
            description_mode=description_mode,
            title=estimate.title,
            services=services,
        )

    @staticmethod
    async def delete_estimate(
        session: AsyncSession,
        estimate_id: int,
        tenant_scope: TenantScope | None = None,
    ) -> ManagerActionMessageResponse:
        deleted = await ServiceEstimateDAO.delete_by_id(
            session=session,
            estimate_id=estimate_id,
            tenant_scope=tenant_scope,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Estimate #{estimate_id} not found",
            )
        return ManagerActionMessageResponse(message=f"Estimate #{estimate_id} deleted")
