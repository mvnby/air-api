import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import func, or_, and_, delete, inspect
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import NO_VALUE, flag_modified

from crud.order import OrderDAO
from crud.product import ProductDAO
from models import Order, OrderProductLink, OrderProposal, OrderServiceLink, Customer, CustomerType, OrderStageStatus, OrderStatus, PaymentCurrency, Product, LeadSource, Service, ServiceTariff, OrderInstaller, OrderWorkStage, Payment
from models.common import ClosingResult
from services.product_supply_metrics_service import ProductSupplyMetricsService
from services.product_area import area_from_specs
from services.order_proposal_lifecycle import (
    PROPOSAL_STATUS_SENT,
)
from services.tenant_scope_service import (
    TenantScope,
    tenant_scope_clause,
)
from services.tenant_entity_access_service import TenantEntityAccessService

logger = logging.getLogger(__name__)

class OrderService:
    MANAGER_LABELS_META_KEY = "manager_labels"
    LEGACY_WEBSITE_TITLE_PREFIX = "Заказ с сайта от "
    ORDER_WORKFLOW_TYPES = {"sales_installation", "service_work", "maintenance", "repair"}
    REPAIR_META_KEY = "repair"
    REPAIR_STATUS_KEY = "repair_status"
    REPAIR_DEFAULT_STATUS = "new"
    REPAIR_WORKFLOW_STATUSES = (
        "new",
        "scheduled",
        "diagnostic_in_progress",
        "awaiting_diagnostic_result",
        "awaiting_customer_approval",
        "approved_for_repair",
        "repair_in_progress",
        "awaiting_parts",
        "completed",
        "not_repairable",
        "cancelled",
    )
    REPAIR_WORKFLOW_STATUS_SET = set(REPAIR_WORKFLOW_STATUSES)
    REPAIR_BOOLEAN_META_KEYS = {"repair_possible", "repair_not_viable"}
    REPAIR_TRUE_VALUES = {"1", "true", "yes", "y", "да", "д", "истина"}
    REPAIR_FALSE_VALUES = {"0", "false", "no", "n", "нет", "н", "ложь"}
    SERVICE_TYPE_TITLE_MAP = {
        "turnkey": "Продажа + монтаж",
        "install_only": "Монтаж",
        "pre_install": "Закладка трассы",
        "maintenance": "Обслуживание",
        "repair": "Ремонт",
        "dismantling": "Демонтаж",
    }
    LOGISTICS_COMPONENT_KINDS = {"indoor", "outdoor", "accessory", "other"}
    DEFAULT_LOGISTICS_COUNTRY = "Китай"
    NEGOTIATION_STATUSES = {
        "awaiting_offer",
        "awaiting_visit",
        "proposal_sent",
        "awaiting_signature",
        "awaiting_payment",
        "follow_up",
    }
    DEFAULT_NEGOTIATION_STATUS = "awaiting_offer"
    EXECUTION_STATUSES = {
        "order_equipment",
        "awaiting_equipment",
        "needs_schedule",
        "scheduled",
        "work_done",
        "awaiting_documents",
        "awaiting_payment",
    }
    DEFAULT_EXECUTION_STATUS = "needs_schedule"
    PAYMENT_COMPLETE_TOLERANCE = 0.01

    @staticmethod
    def _normalize_negotiation_status(value: Any, fallback: str = DEFAULT_NEGOTIATION_STATUS) -> str:
        cleaned = str(value or "").strip()
        if cleaned in OrderService.NEGOTIATION_STATUSES:
            return cleaned
        return fallback if fallback in OrderService.NEGOTIATION_STATUSES else OrderService.DEFAULT_NEGOTIATION_STATUS

    @staticmethod
    def _normalize_execution_status(value: Any, fallback: str = DEFAULT_EXECUTION_STATUS) -> str:
        cleaned = str(value or "").strip()
        if cleaned in OrderService.EXECUTION_STATUSES:
            return cleaned
        return fallback if fallback in OrderService.EXECUTION_STATUSES else OrderService.DEFAULT_EXECUTION_STATUS

    @staticmethod
    def _status_value(value: Any) -> str:
        if hasattr(value, "value"):
            return str(value.value)
        return str(value or "").strip()

    @staticmethod
    def _infer_execution_status(order: Order) -> str:
        raw_status = getattr(order, "execution_status", None)
        if raw_status is not None:
            current = str(raw_status or "").strip()
            if current in OrderService.EXECUTION_STATUSES:
                return current
        if order.status != OrderStatus.EXECUTION:
            return OrderService.DEFAULT_EXECUTION_STATUS
        if order.installation_date:
            return "scheduled"
        return OrderService.DEFAULT_EXECUTION_STATUS

    @staticmethod
    def _set_execution_status(order: Order, value: Any, *, changed_at: Optional[datetime] = None) -> None:
        next_status = str(value or "").strip()
        if next_status not in OrderService.EXECUTION_STATUSES:
            raise ValueError(f"Invalid execution_status: {value}")
        previous = OrderService._normalize_execution_status(getattr(order, "execution_status", None))
        order.execution_status = next_status
        if previous != next_status or not getattr(order, "execution_status_changed_at", None):
            order.execution_status_changed_at = changed_at or datetime.now()

    @staticmethod
    def _infer_negotiation_status(order: Order) -> str:
        raw_status = getattr(order, "negotiation_status", None)
        if raw_status is not None:
            current = str(raw_status or "").strip()
            if current in OrderService.NEGOTIATION_STATUSES:
                return current
        if order.status != OrderStatus.NEGOTIATION:
            return OrderService.DEFAULT_NEGOTIATION_STATUS
        if order.proposal_status == "sent":
            return "proposal_sent"
        if order.proposal_status == "approved" and not order.is_paid:
            return "awaiting_payment"
        if order.measurement_required:
            return "awaiting_visit"
        return OrderService.DEFAULT_NEGOTIATION_STATUS

    @staticmethod
    def _set_negotiation_status(order: Order, value: Any, *, changed_at: Optional[datetime] = None) -> None:
        next_status = str(value or "").strip()
        if next_status not in OrderService.NEGOTIATION_STATUSES:
            raise ValueError(f"Invalid negotiation_status: {value}")
        previous = OrderService._normalize_negotiation_status(getattr(order, "negotiation_status", None))
        order.negotiation_status = next_status
        if previous != next_status or not getattr(order, "negotiation_status_changed_at", None):
            order.negotiation_status_changed_at = changed_at or datetime.now()

    @staticmethod
    def _clean_optional_text(value: Any) -> Optional[str]:
        cleaned = " ".join(str(value or "").split())
        return cleaned or None

    @staticmethod
    def _extract_product_country(product: Optional[Product]) -> Optional[str]:
        specs = getattr(product, "specs", None)
        if not isinstance(specs, dict):
            return None
        for key in ("country", "country_of_origin", "Страна производства", "Страна-производитель"):
            country = OrderService._clean_optional_text(specs.get(key))
            if country:
                return country
        return None

    @staticmethod
    def _serialize_product_logistics_components(product: Optional[Product]) -> List[Dict[str, Any]]:
        specs = getattr(product, "specs", None)
        if not isinstance(specs, dict):
            return []
        raw_components = specs.get("logistics_components")
        if not isinstance(raw_components, list):
            return []

        out: List[Dict[str, Any]] = []
        for item in raw_components:
            if not isinstance(item, dict):
                continue
            title = OrderService._clean_optional_text(item.get("title"))
            if not title:
                continue
            country = OrderService._clean_optional_text(item.get("country"))
            unit = OrderService._clean_optional_text(item.get("unit")) or "шт."
            try:
                quantity_per_parent = max(1, int(float(item.get("quantity_per_parent") or 1)))
            except (TypeError, ValueError):
                quantity_per_parent = 1
            try:
                price_weight = max(0.0, float(item.get("price_weight") or 1))
            except (TypeError, ValueError):
                price_weight = 1.0
            kind = OrderService._clean_optional_text(item.get("kind"))
            if kind not in OrderService.LOGISTICS_COMPONENT_KINDS:
                kind = None
            out.append(
                {
                    "title": title,
                    "country": country,
                    "unit": unit,
                    "quantity_per_parent": quantity_per_parent,
                    "price_weight": price_weight,
                    "kind": kind,
                }
            )
        return out

    @staticmethod
    def _serialize_order_logistics_components(raw_components: Any) -> Optional[List[Dict[str, Any]]]:
        if not raw_components:
            return None

        out: List[Dict[str, Any]] = []
        for item in raw_components:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if not isinstance(item, dict):
                continue
            title = OrderService._clean_optional_text(item.get("title"))
            if not title:
                continue
            country = OrderService._clean_optional_text(item.get("country"))
            unit = OrderService._clean_optional_text(item.get("unit")) or "шт."
            try:
                quantity_per_parent = max(1, int(float(item.get("quantity_per_parent") or 1)))
            except (TypeError, ValueError):
                quantity_per_parent = 1
            try:
                unit_price = max(0.0, float(item.get("unit_price") or 0))
            except (TypeError, ValueError):
                unit_price = 0.0
            kind = OrderService._clean_optional_text(item.get("kind"))
            if kind not in OrderService.LOGISTICS_COMPONENT_KINDS:
                kind = None
            out.append(
                {
                    "title": title,
                    "country": country,
                    "unit": unit,
                    "quantity_per_parent": quantity_per_parent,
                    "unit_price": unit_price,
                    "kind": kind,
                }
            )
        return out or None

    @staticmethod
    def _order_logistics_to_product_template(raw_components: Any) -> List[Dict[str, Any]]:
        components = OrderService._serialize_order_logistics_components(raw_components)
        if not components:
            return []

        out: List[Dict[str, Any]] = []
        for item in components:
            quantity_per_parent = int(item.get("quantity_per_parent") or 1)
            try:
                price_weight = float(item.get("unit_price") or 0) * quantity_per_parent
            except (TypeError, ValueError):
                price_weight = 0.0
            out.append(
                {
                    "title": item["title"],
                    "country": item.get("country"),
                    "unit": item.get("unit") or "шт.",
                    "quantity_per_parent": quantity_per_parent,
                    "price_weight": price_weight if price_weight > 0 else 1.0,
                    "kind": item.get("kind"),
                }
            )
        return out

    @staticmethod
    async def _backfill_product_logistics_template(
        session: AsyncSession,
        product_id: Optional[int],
        raw_components: Any,
    ) -> None:
        if not product_id or not raw_components:
            return
        template_components = OrderService._order_logistics_to_product_template(raw_components)
        if not template_components:
            return

        product = await session.get(Product, product_id)
        if not product:
            return
        if OrderService._serialize_product_logistics_components(product):
            return

        specs = dict(product.specs or {})
        specs["logistics_components"] = template_components
        product.specs = specs
        flag_modified(product, "specs")
        session.add(product)

    @staticmethod
    def _clean_order_title(raw: Any) -> Optional[str]:
        title = " ".join(str(raw or "").split())
        return title or None

    @staticmethod
    def _display_order_title(order: Order) -> Optional[str]:
        title = OrderService._clean_order_title(order.title)
        if title and title.startswith(OrderService.LEGACY_WEBSITE_TITLE_PREFIX):
            return None
        return title

    @staticmethod
    def _map_payment(payment: Payment) -> Dict[str, Any]:
        receipt_value = inspect(payment).attrs.bank_receipt.loaded_value
        receipt = receipt_value if receipt_value is not NO_VALUE else None
        receipt_data = None
        if receipt:
            receipt_data = {
                "id": receipt.id,
                "status": receipt.status,
                "received_at": receipt.received_at,
                "amount": float(receipt.amount),
                "currency": receipt.currency,
                "payer_name": receipt.payer_name,
                "payer_unp": receipt.payer_unp,
                "payer_account": receipt.payer_account,
                "payment_document_raw": receipt.payment_document_raw,
                "payment_document_number": receipt.payment_document_number,
                "payment_purpose": receipt.payment_purpose,
            }
        return {
            "id": payment.id,
            "amount": float(payment.amount),
            "currency": payment.currency.value if hasattr(payment.currency, "value") else str(payment.currency),
            "date": payment.date,
            "type": payment.type.value if hasattr(payment.type, "value") else str(payment.type),
            "comment": payment.comment,
            "created_at": payment.created_at,
            "bank_receipt_id": payment.bank_receipt_id,
            "bank_receipt": receipt_data,
        }

    @staticmethod
    def _build_default_order_title(
        *,
        service_type: Optional[str] = None,
        comment: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        if service_type:
            mapped = OrderService.SERVICE_TYPE_TITLE_MAP.get(str(service_type))
            if mapped:
                return mapped

        text = str(comment or "").casefold()
        if any(marker in text for marker in ("обслуж", "сервис", " то ", "техобслуж")):
            return "Обслуживание"
        if any(marker in text for marker in ("ремонт", "чинит", "не работает", "ошибк")):
            return "Ремонт"
        if "демонтаж" in text:
            return "Демонтаж"
        if any(marker in text for marker in ("монтаж", "установ")):
            return "Монтаж"
        if any(marker in text for marker in ("заклад", "трасс")):
            return "Закладка трассы"
        if any(marker in text for marker in ("куп", "покуп", "продаж", "кондиционер")):
            return "Продажа"

        if items:
            has_installation = any(bool(item.get("with_installation")) for item in items)
            return "Продажа + монтаж" if has_installation else "Продажа"

        return None

    @staticmethod
    def _json_text_search_variants(raw: str) -> List[str]:
        text = str(raw or "").strip()
        if not text:
            return []

        variants = [text]
        escaped = json.dumps(text, ensure_ascii=True)[1:-1]
        if escaped and escaped not in variants:
            variants.append(escaped)
            like_escaped = escaped.replace("\\", "\\\\")
            if like_escaped not in variants:
                variants.append(like_escaped)
        return variants

    @staticmethod
    def _normalize_manager_labels(raw_labels: Any) -> List[str]:
        if not isinstance(raw_labels, list):
            return []

        labels: List[str] = []
        seen: set[str] = set()
        for raw in raw_labels:
            label = " ".join(str(raw or "").split())
            if not label:
                continue
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
        return labels

    @staticmethod
    def _get_manager_labels(order: Order) -> List[str]:
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        return OrderService._normalize_manager_labels(meta.get(OrderService.MANAGER_LABELS_META_KEY))

    @staticmethod
    def _workflow_type_from_service_type(service_type: Optional[str], fallback: str = "sales_installation") -> str:
        mapping = {
            "turnkey": "sales_installation",
            "install_only": "service_work",
            "pre_install": "service_work",
            "dismantling": "service_work",
            "maintenance": "maintenance",
            "repair": "repair",
        }
        return mapping.get(str(service_type or "").strip(), fallback)

    @staticmethod
    def _normalize_workflow_type(raw: Any, fallback: str = "sales_installation") -> str:
        value = str(raw or "").strip()
        if value in OrderService.ORDER_WORKFLOW_TYPES:
            return value
        if value:
            service_mapped = OrderService._workflow_type_from_service_type(value, "")
            if service_mapped:
                return service_mapped
        return fallback

    @staticmethod
    def normalize_repair_status(raw: Any, fallback: Optional[str] = None) -> str:
        value = str(raw or "").strip()
        if not value:
            if fallback is not None:
                return OrderService.normalize_repair_status(fallback)
            raise ValueError(f"{OrderService.REPAIR_STATUS_KEY} is required")

        normalized = "_".join(value.casefold().replace("-", "_").split())
        if normalized not in OrderService.REPAIR_WORKFLOW_STATUS_SET:
            allowed = ", ".join(OrderService.REPAIR_WORKFLOW_STATUSES)
            raise ValueError(f"Invalid {OrderService.REPAIR_STATUS_KEY}: {raw}. Allowed: {allowed}")
        return normalized

    @staticmethod
    def _normalize_repair_boolish(raw: Any) -> Any:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            value = raw.strip()
            lowered = value.casefold()
            if lowered in OrderService.REPAIR_TRUE_VALUES:
                return True
            if lowered in OrderService.REPAIR_FALSE_VALUES:
                return False
            return value
        return raw

    @staticmethod
    def normalize_repair_meta(raw_meta: Any, default_status: Optional[str] = None) -> Dict[str, Any]:
        if not isinstance(raw_meta, dict):
            cleaned: Dict[str, Any] = {}
        else:
            cleaned = {}
            for raw_key, raw_value in raw_meta.items():
                key = str(raw_key or "").strip()
                if not key or raw_value is None:
                    continue
                if isinstance(raw_value, str):
                    value: Any = raw_value.strip()
                    if not value:
                        continue
                else:
                    value = raw_value

                if key == OrderService.REPAIR_STATUS_KEY:
                    cleaned[key] = OrderService.normalize_repair_status(value, fallback=default_status)
                elif key in OrderService.REPAIR_BOOLEAN_META_KEYS:
                    cleaned[key] = OrderService._normalize_repair_boolish(value)
                else:
                    cleaned[key] = value

        if OrderService.REPAIR_STATUS_KEY not in cleaned and default_status is not None:
            cleaned[OrderService.REPAIR_STATUS_KEY] = OrderService.normalize_repair_status(default_status)
        return cleaned

    @staticmethod
    def _get_repair_meta(order: Order) -> Dict[str, Any]:
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        repair_meta = meta.get(OrderService.REPAIR_META_KEY)
        raw = dict(repair_meta) if isinstance(repair_meta, dict) else {}
        if OrderService._normalize_workflow_type(getattr(order, "workflow_type", None)) != "repair":
            return raw
        try:
            return OrderService.normalize_repair_meta(raw, default_status=OrderService.REPAIR_DEFAULT_STATUS)
        except ValueError:
            logger.warning("Order %s has invalid repair meta status", getattr(order, "id", None))
            return raw

    @staticmethod
    def _set_repair_meta(
        order: Order,
        raw_meta: Any,
        default_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        meta = dict(order.technical_meta or {}) if isinstance(order.technical_meta, dict) else {}
        cleaned = OrderService.normalize_repair_meta(raw_meta, default_status=default_status)
        if cleaned:
            meta[OrderService.REPAIR_META_KEY] = cleaned
        else:
            meta.pop(OrderService.REPAIR_META_KEY, None)
        order.technical_meta = meta
        return cleaned

    @staticmethod
    def _ensure_repair_meta_defaults(order: Order) -> Dict[str, Any]:
        if OrderService._normalize_workflow_type(getattr(order, "workflow_type", None)) != "repair":
            return OrderService._get_repair_meta(order)
        return OrderService._set_repair_meta(
            order,
            OrderService._get_repair_meta(order),
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )

    @staticmethod
    def _ensure_repair_workflow(order: Order) -> None:
        if OrderService._normalize_workflow_type(getattr(order, "workflow_type", None)) != "repair":
            raise ValueError("Repair workflow transitions can only be applied to repair orders")

    @staticmethod
    def set_repair_workflow_status(
        order: Order,
        status: Any,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        OrderService._ensure_repair_workflow(order)
        repair_meta = OrderService._get_repair_meta(order)
        if extra_meta:
            repair_meta.update(extra_meta)
        repair_meta[OrderService.REPAIR_STATUS_KEY] = status
        return OrderService._set_repair_meta(
            order,
            repair_meta,
            default_status=OrderService.REPAIR_DEFAULT_STATUS,
        )

    @staticmethod
    def mark_repair_diagnostic_in_progress(order: Order) -> Dict[str, Any]:
        return OrderService.set_repair_workflow_status(order, "diagnostic_in_progress")

    @staticmethod
    def mark_repair_awaiting_diagnostic_result(order: Order) -> Dict[str, Any]:
        return OrderService.set_repair_workflow_status(order, "awaiting_diagnostic_result")

    @staticmethod
    def record_repair_diagnostic_result(
        order: Order,
        diagnostic_result: Any,
        *,
        repair_recommendation: Any = None,
        repair_possible: Any = None,
        next_status: str = "awaiting_customer_approval",
    ) -> Dict[str, Any]:
        updates = {"diagnostic_result": diagnostic_result}
        if repair_recommendation is not None:
            updates["repair_recommendation"] = repair_recommendation
        if repair_possible is not None:
            updates["repair_possible"] = repair_possible
        return OrderService.set_repair_workflow_status(order, next_status, updates)

    @staticmethod
    def mark_repair_awaiting_customer_approval(order: Order, note: Any = None) -> Dict[str, Any]:
        updates = {"customer_approval_status": "pending"}
        if note is not None:
            updates["customer_approval_note"] = note
        return OrderService.set_repair_workflow_status(order, "awaiting_customer_approval", updates)

    @staticmethod
    def mark_repair_approved_for_repair(order: Order, note: Any = None) -> Dict[str, Any]:
        updates = {"customer_approval_status": "approved"}
        if note is not None:
            updates["customer_approval_note"] = note
        return OrderService.set_repair_workflow_status(order, "approved_for_repair", updates)

    @staticmethod
    def mark_repair_in_progress(order: Order) -> Dict[str, Any]:
        return OrderService.set_repair_workflow_status(order, "repair_in_progress")

    @staticmethod
    def mark_repair_awaiting_parts(order: Order, note: Any = None) -> Dict[str, Any]:
        updates = {"parts_status": "awaiting"}
        if note is not None:
            updates["parts_note"] = note
        return OrderService.set_repair_workflow_status(order, "awaiting_parts", updates)

    @staticmethod
    def mark_repair_completed(order: Order, note: Any = None) -> Dict[str, Any]:
        updates = {"repair_completion_note": note} if note is not None else None
        return OrderService.set_repair_workflow_status(order, "completed", updates)

    @staticmethod
    def mark_repair_not_repairable(
        order: Order,
        reason: Any = None,
        *,
        diagnostic_result: Any = None,
    ) -> Dict[str, Any]:
        updates: Dict[str, Any] = {
            "repair_possible": False,
            "repair_not_viable": True,
        }
        if reason is not None:
            updates["repair_not_viable_reason"] = reason
        if diagnostic_result is not None:
            updates["diagnostic_result"] = diagnostic_result
        return OrderService.set_repair_workflow_status(order, "not_repairable", updates)

    @staticmethod
    def _set_manager_labels(order: Order, raw_labels: Any) -> None:
        meta = dict(order.technical_meta or {}) if isinstance(order.technical_meta, dict) else {}
        labels = OrderService._normalize_manager_labels(raw_labels)
        if labels:
            meta[OrderService.MANAGER_LABELS_META_KEY] = labels
        else:
            meta.pop(OrderService.MANAGER_LABELS_META_KEY, None)
        order.technical_meta = meta

    @staticmethod
    def _normalize_payment_currency(raw: Any) -> PaymentCurrency:
        if isinstance(raw, PaymentCurrency):
            return raw
        try:
            return PaymentCurrency(str(raw).upper())
        except Exception as exc:
            raise ValueError(f"Invalid payment currency: {raw}") from exc

    @staticmethod
    async def _refresh_order_financials(session: AsyncSession, order: Order) -> None:
        await session.refresh(order, attribute_names=["payments", "proposals", "product_links", "service_links", "installers"])
        order.calculate_totals()
        OrderService._apply_payment_state(order)

    @staticmethod
    def _apply_payment_state(order: Order) -> None:
        if float(order.total_amount or 0) <= 0:
            return
        is_fully_paid = float(order.balance_due or 0) <= OrderService.PAYMENT_COMPLETE_TOLERANCE
        order.is_paid = is_fully_paid
        status = OrderService._status_value(order.status)
        if (
            is_fully_paid
            and bool(getattr(order, "auto_execution_on_payment", False))
            and status == OrderStatus.NEGOTIATION.value
        ):
            order.status = OrderStatus.EXECUTION
            status = OrderStatus.EXECUTION.value
            order.status_changed_at = datetime.now()
            order.proposal_status = "approved"
        if (
            is_fully_paid
            and bool(getattr(order, "auto_close_on_payment", False))
            and status == OrderStatus.EXECUTION.value
            and OrderService._normalize_execution_status(getattr(order, "execution_status", None)) == "awaiting_payment"
        ):
            order.status = OrderStatus.CLOSED
            order.closing_result = ClosingResult.WON.value
            order.reject_reason = None
            order.closed_at = datetime.now()
            order.status_changed_at = datetime.now()

    @staticmethod
    def _clean_proposal_name(raw: Any, fallback: str = "Основное") -> str:
        name = " ".join(str(raw or "").split())
        return name or fallback

    @staticmethod
    def _proposal_line_totals(product_links: List[OrderProductLink], service_links: List[OrderServiceLink]) -> tuple[float, float, float]:
        total_amount = float(
            sum((link.price or 0) * (link.quantity or 0) for link in product_links)
            + sum((link.price or 0) * (link.quantity or 0) for link in service_links)
        )
        total_cost = float(
            sum((link.cost or 0) * (link.quantity or 0) for link in product_links)
            + sum((link.cost or 0) * (link.quantity or 0) for link in service_links)
        )
        return total_amount, total_cost, total_amount - total_cost

    @staticmethod
    def _selected_proposal(order: Order) -> Optional[OrderProposal]:
        active = [proposal for proposal in getattr(order, "proposals", []) if not proposal.is_archived]
        return (
            next((proposal for proposal in active if proposal.is_selected), None)
            or next(iter(sorted(active, key=lambda proposal: proposal.sort_order)), None)
        )

    @staticmethod
    def _legacy_default_proposal_status(order: Order) -> str:
        """Only carry forward a legacy status when there is evidence of sending."""
        if order.proposal_status == PROPOSAL_STATUS_SENT and order.proposal_sent_at:
            return PROPOSAL_STATUS_SENT
        return "draft"

    @staticmethod
    async def ensure_default_proposal(session: AsyncSession, order: Order) -> OrderProposal:
        proposals = list(getattr(order, "proposals", []) or [])
        active = [proposal for proposal in proposals if not proposal.is_archived]
        if active:
            selected = OrderService._selected_proposal(order)
            if selected and not selected.is_selected:
                for proposal in proposals:
                    proposal.is_selected = proposal.id == selected.id
                    session.add(proposal)
                await session.flush()
            return selected or active[0]

        proposal = OrderProposal(
            order_id=int(order.id),
            name="Основное",
            status=OrderService._legacy_default_proposal_status(order),
            is_selected=True,
            sort_order=0,
        )
        session.add(proposal)
        await session.flush()
        await session.execute(
            OrderProductLink.__table__.update()
            .where(OrderProductLink.order_id == order.id, OrderProductLink.proposal_id.is_(None))
            .values(proposal_id=proposal.id)
        )
        await session.execute(
            OrderServiceLink.__table__.update()
            .where(OrderServiceLink.order_id == order.id, OrderServiceLink.proposal_id.is_(None))
            .values(proposal_id=proposal.id)
        )
        await session.refresh(order, attribute_names=["proposals", "product_links", "service_links"])
        return proposal

    @staticmethod
    async def _get_product_purchase_cost(
        session: AsyncSession,
        product: Product,
        cache: Optional[Dict[int, int]] = None,
    ) -> int:
        product_id = int(product.id or 0)
        if product_id <= 0:
            return 0
        if cache is not None and product_id in cache:
            return cache[product_id]

        metrics = await ProductSupplyMetricsService.compute_for_products(session, [product])
        raw_cost = (metrics.get(product_id) or {}).get("min_cost_byn")
        cost = int(round(float(raw_cost))) if raw_cost is not None else 0

        if cache is not None:
            cache[product_id] = cost
        return cost

    @staticmethod
    def _normalize_naive_datetime(dt: Optional[datetime]) -> Optional[datetime]:
        """Convert timezone-aware datetime to naive (for DB compatibility)."""
        if dt is not None and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    @staticmethod
    def _normalize_order_stage_status(raw: Any, fallback: OrderStageStatus = OrderStageStatus.PLANNED) -> OrderStageStatus:
        value = raw if raw is not None else fallback
        if isinstance(value, OrderStageStatus):
            return value
        try:
            return OrderStageStatus(str(value))
        except ValueError as exc:
            allowed = ", ".join(item.value for item in OrderStageStatus)
            raise ValueError(f"Invalid work stage status: {raw}. Allowed: {allowed}") from exc

    @staticmethod
    async def get_calendar_events(
        session: AsyncSession,
        start_date: datetime,
        end_date: datetime,
        *,
        tenant_scope: TenantScope,
    ) -> List["CalendarEventResponse"]:
        """
        Get calendar events for orders (assessments and installations).
        """
        from schemas import CalendarEventResponse, CalendarEventType
        from models import OrderWorkStage
        
        # Adjust end_date to include the full day if needed, or rely on caller
        
        # Ensure dates are offset-naive for PostgreSQL comparison if DB stores naive timestamps
        if start_date.tzinfo is not None:
            start_date = start_date.replace(tzinfo=None)
        if end_date.tzinfo is not None:
            end_date = end_date.replace(tzinfo=None)

        # Query orders where EITHER measurement_date OR installation_date OR work_stage is in range
        stmt = (
            select(Order)
            .outerjoin(OrderWorkStage, Order.id == OrderWorkStage.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
                or_(
                    and_(Order.measurement_date >= start_date, Order.measurement_date <= end_date),
                    and_(Order.installation_date >= start_date, Order.installation_date <= end_date),
                    and_(OrderWorkStage.start_time >= start_date, OrderWorkStage.start_time <= end_date)
                )
            )
            .distinct(Order.id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.work_stages).selectinload(OrderWorkStage.installer)
            )
        )
        
        result = await session.execute(stmt)
        orders = result.scalars().all()
        
        events = []
        
        for order in orders:
            # Measurement Event
            if order.measurement_date and start_date <= order.measurement_date <= end_date:
                events.append(CalendarEventResponse(
                    id=f"{order.id}-measurement",
                    order_id=order.id,
                    type=CalendarEventType.MEASUREMENT,
                    date=order.measurement_date,
                    status=order.status.value if hasattr(order.status, "value") else str(order.status),
                    customer_name=order.customer.name if order.customer else "Неизвестный",
                    address=order.delivery_address,
                    title=f"Замер: {order.customer.name if order.customer else 'Клиент'}",
                    start=order.measurement_date,
                    color="#64748b" # Slate
                ))
            
            # Installation Event
            if order.installation_date and start_date <= order.installation_date <= end_date:
                 events.append(CalendarEventResponse(
                    id=f"{order.id}-installation",
                    order_id=order.id,
                    type=CalendarEventType.INSTALLATION,
                    date=order.installation_date,
                    status=order.status.value if hasattr(order.status, "value") else str(order.status),
                    customer_name=order.customer.name if order.customer else "Неизвестный",
                    address=order.delivery_address,
                    title=f"Монтаж: {order.customer.name if order.customer else 'Клиент'}",
                    start=order.installation_date,
                    color="#007f80" # Teal
                ))
            
            # Work Stage Events
            for stage in order.work_stages:
                if stage.start_time and start_date <= stage.start_time <= end_date:
                    st_val = stage.status.value if hasattr(stage.status, "value") else str(stage.status)
                    color = "#0ea5e9" # Sky-500 default
                    title = stage.name
                    if st_val == "completed":
                        color = "#10b981" # Emerald-500
                    elif st_val == "canceled":
                        color = "#94a3b8" # Slate-400
                        title = f"Отменен: {stage.name}"

                    title += f" - {order.customer.name if order.customer else 'Клиент'}"
                        
                    events.append(CalendarEventResponse(
                        id=f"{order.id}-stage-{stage.id}",
                        order_id=order.id,
                        type=CalendarEventType.WORK_STAGE,
                        date=stage.start_time,
                        status=st_val,
                        customer_name=order.customer.name if order.customer else "Неизвестный",
                        address=order.delivery_address,
                        title=title,
                        start=stage.start_time,
                        color=color
                    ))
                
        return events

    @staticmethod
    async def create_order(
        session: AsyncSession,
        user_id: int,
        contact_info: str, # Телефон или адрес
        items_data: Dict[str, Any], # Словарь с товарами
        *,
        tenant_scope: TenantScope,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> Order:
        """
        Create order and populate it with items.
        """
        # 1. Создаем сам заказ
        order = await OrderDAO.create(
            session,
            user_id=user_id,
            tenant_scope=tenant_scope,
            phone=contact_info,
            username=username,
            full_name=full_name,
        )
        
        # 2. Наполняем товарами
        if items_data:
            await OrderService.update_order_links(session, order.id, items_data)
        
        return order

    @staticmethod
    async def create_manager_order(
        session: AsyncSession,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility delegate to the transactional create command."""
        from services.order_create_command_service import OrderCreateCommandService

        return await OrderCreateCommandService.create_manager_order(
            session,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def create_from_website(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        customer_name: str,
        customer_phone: str,
        customer_email: Optional[str],
        customer_address: Optional[str],
        items: List[Dict[str, Any]],  # [{"product_id": int, "quantity": int}]
        lead_source: LeadSource = LeadSource.SITE,
        initial_status: OrderStatus = OrderStatus.NEW_LEAD,
        comment: Optional[str] = None,
        customer_type: str = "individual",
        customer_inn: Optional[str] = None,
        customer_full_legal_name: Optional[str] = None,
        customer_legal_address: Optional[str] = None,
        customer_iban: Optional[str] = None,
        customer_bic: Optional[str] = None,
        customer_bank_name: Optional[str] = None,
        customer_id: Optional[int] = None,
        order_technical_meta: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> Order:
        """
        Create order from website checkout.
        
        Handles:
        1. Customer lookup/creation by phone
        2. Order creation with the requested initial status and lead_source
        3. Product linking with current prices
        4. Total calculation
        
        Args:
            session: Database session
            customer_name: Customer full name
            customer_phone: Phone number (used for lookup)
            customer_email: Optional email
            customer_address: Delivery address
            items: List of cart items [{product_id, quantity}]
            lead_source: Source of the lead (SITE, BOT, PHONE, etc.)
            initial_status: Initial order status in CRM workflow
            comment: Optional note or initial customer request
            
        Returns:
            Created Order with calculated totals
        """
        phone_clean = customer_phone.strip()
        
        # 1. Find or create customer
        customer = None
        
        if customer_id:
            customer = (
                await session.execute(
                    select(Customer).where(
                        Customer.id == customer_id,
                        tenant_scope_clause(
                            Customer,
                            tenant_scope,
                        ),
                    )
                )
            ).scalars().first()
            if not customer:
                raise ValueError(f"Customer with id {customer_id} not found")
        elif len(phone_clean) > 5:
            stmt = select(Customer).where(
                Customer.phone == phone_clean,
                tenant_scope_clause(Customer, tenant_scope),
            )
            result = await session.execute(stmt)
            # Handle potential duplicates gracefully
            try:
                customer = result.scalar_one_or_none()
            except Exception:
                logger.warning(
                    "CUSTOMER_LOOKUP_MULTIPLE_MATCHES source=%s creating_new=true",
                    lead_source.value,
                )
                customer = None
        
        if not customer:
            customer = Customer(
                tenant_id=tenant_scope.tenant_id,
                name=customer_name,
                phone=phone_clean,
                email=customer_email,
                type=CustomerType.company if customer_type == "company" else CustomerType.individual,
                actual_address=customer_address,
                inn=customer_inn,
                full_legal_name=customer_full_legal_name,
                legal_address=customer_legal_address,
                iban=customer_iban,
                bic=customer_bic,
                bank_name=customer_bank_name
            )
            session.add(customer)
            await session.flush()
            logger.info(
                "CUSTOMER_CREATED customer_id=%s source=%s",
                customer.id,
                lead_source.value,
            )
        else:
            if customer.tenant_id is None:
                customer.tenant_id = tenant_scope.tenant_id
            # Update address if provided
            if customer_address:
                customer.actual_address = customer_address
            
            # Update B2B info if provided (individual -> company conversion or updating company data)
            if customer_type == "company":
                customer.type = CustomerType.company
                if customer_inn:
                    customer.inn = customer_inn
                if customer_full_legal_name:
                    customer.full_legal_name = customer_full_legal_name
                if customer_legal_address:
                    customer.legal_address = customer_legal_address
                if customer_iban:
                    customer.iban = customer_iban
                if customer_bic:
                    customer.bic = customer_bic
                if customer_bank_name:
                    customer.bank_name = customer_bank_name
            
            session.add(customer)

        # 2. Create order with lead_source
        default_title = OrderService._build_default_order_title(comment=comment, items=items)
        order = Order(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            customer_id=customer.id,
            delivery_address=customer_address,
            status=initial_status,
            lead_source=lead_source,
            comment=comment,
            title=default_title,
            technical_meta=dict(order_technical_meta or {}),
            created_at=datetime.now(),
            status_changed_at=datetime.now(),
        )
        session.add(order)
        await session.flush()
        proposal = OrderProposal(
            order_id=int(order.id),
            name="Основное",
            status="draft",
            is_selected=True,
            sort_order=0,
        )
        session.add(proposal)
        await session.flush()
        
        # 3. Add items with current prices
        total_amount = 0.0
        added_items = []
        installation_services = []  # Collect installation services to add after products
        product_cost_cache: Dict[int, int] = {}
        
        for item in items:
            product_id = item.get("product_id")
            product = None


# ...

            if product_id:
                product = await ProductDAO.get_by_id(session, product_id)

            if product:
                # Extract installation fields (Phase: Snapshot Pricing Refactor)
                with_installation = item.get("with_installation", False)
                installation_price = int(item.get("installation_price", 0))
                product_cost = await OrderService._get_product_purchase_cost(
                    session,
                    product,
                    product_cost_cache,
                )
                
                link = OrderProductLink(
                    order_id=order.id,
                    proposal_id=proposal.id,
                    product_id=product.id,
                    quantity=item["quantity"],
                    price=product.price,
                    cost=product_cost,
                    # Save snapshot for history
                    is_installation_included=with_installation,
                    installation_price=installation_price if with_installation else 0,
                    installation_details=item.get("installation_meta") if with_installation else None
                )
                session.add(link)
                
                # Calculate product total
                product_total = product.price * item["quantity"]
                total_amount += product_total
                
                # If installation requested, add to total
                if with_installation and installation_price > 0:
                    total_amount += installation_price * item["quantity"]
                    
                    # --- NEW LOGIC: Explicitly create OrderServiceLink for Main Installation ---
                    # Construct title based on meta
                    meta = item.get("installation_meta", {})
                    meters = meta.get("meters", 3)
                    type_raw = meta.get("type", "General")
                    power_raw = meta.get("power_range", "")
                    
                    
                    # Robust Title Generation using Product Attributes + Mappings
                    # User requested format: "Монтаж кондиционера {type}, мощностью {power}, включая межблочную трассу {meters} м"
                    
                    # 1. Determine Type
                    # Mappings: Wall -> настенного типа, Cassette -> кассетного типа, etc.
                    # We check: product tags, meta type, or fallback to Wall.
                    type_str = "настенного типа" # Default
                    
                    # Try to find type in tags if product exists
                    product_tags_titles = [t.title.lower() for t in product.tags] if product and product.tags else []
                    product_tags_slugs = [t.slug.lower() for t in product.tags] if product and product.tags else []
                    
                    # Map of tag/meta keywords to Russian text
                    TYPE_MAPPINGS = {
                        'wall': 'настенного типа', 
                        'настенный': 'настенного типа',
                        'cassette': 'кассетного типа', 
                        'кассетный': 'кассетного типа',
                        'ceiling': 'потолочного типа', 
                        'напольно-потолочный': 'потолочного типа',
                        'duct': 'канального типа', 
                        'канальный': 'канального типа',
                        'multisplit': 'мульти-сплит системы',
                        'multi': 'мульти-сплит системы'
                    }
                    
                    # Check tags first (more reliable than meta usually)
                    found_type = False
                    for key, val in TYPE_MAPPINGS.items():
                        if key in product_tags_slugs or key in product_tags_titles:
                            type_str = val
                            found_type = True
                            break
                    
                    # If not found in tags, check meta (fallback)
                    if not found_type and type_raw and type_raw != "General":
                        lower_raw = type_raw.lower()
                        if lower_raw in TYPE_MAPPINGS:
                            type_str = TYPE_MAPPINGS[lower_raw]
                        else:
                             # Direct translation check for common English terms
                             if 'wall' in lower_raw: type_str = 'настенного типа'
                             elif 'cassette' in lower_raw: type_str = 'кассетного типа'
                             elif 'ceiling' in lower_raw: type_str = 'потолочного типа'
                             elif 'duct' in lower_raw: type_str = 'канального типа'
                             elif 'multi' in lower_raw: type_str = 'мульти-сплит системы'

                    # 2. Determine Power Range
                    # Mappings: 
                    # area-20..35 -> до 4 кВт
                    # area-50..70 -> до 7 кВт
                    # area-80+ -> выше 7 кВт
                    power_str = ""
                    
                    # Use product area if available
                    area = area_from_specs(product.specs) if product else None
                    if area:
                        if area <= 35:
                            power_str = "до 4 кВт"
                        elif area <= 70:
                            power_str = "до 7 кВт"
                        else:
                            power_str = "выше 7 кВт"
                    elif power_raw:
                        # Fallback to meta string parsing if product area missing
                        # power_raw ex: "area-25", "07-12", "Standard"
                        if "20" in power_raw or "25" in power_raw or "35" in power_raw or "07" in power_raw or "09" in power_raw or "12" in power_raw:
                             power_str = "до 4 кВт"
                        elif "50" in power_raw or "70" in power_raw or "18" in power_raw or "24" in power_raw:
                             power_str = "до 7 кВт"
                        elif "80" in power_raw or "100" in power_raw or "30" in power_raw or "36" in power_raw:
                             power_str = "выше 7 кВт"
                        # Handle specific text map from old logic if needed, but above covers most numeric codes

                    # Construct Title
                    main_inst_title = f"Монтаж кондиционера {type_str}"
                    if power_str:
                        main_inst_title += f", мощностью {power_str}"
                    
                    main_inst_title += f", включая межблочную трассу {meters} м"


                    # Add MAIN installation as a service link
                    installation_services.append({
                        "title": main_inst_title,
                        "price": installation_price, # This is the calculated total for main install (base + meters)
                        "quantity": item["quantity"]
                    })
                    
                    # --- NEW LOGIC: Process Add-ons ---
                    options_slugs = item.get("installation_options", [])
                    if options_slugs:
                        # Fetch services by slug to get titles/prices (security check)
                        # Note: The price in payload "installation_price" usually includes options if calculated on frontend.
                        # However, for accurate breakdown, we should ideally sum them up or use the frontend provided breakdown if available.
                        # Current cart.ts logic: "installationPrice" holds the SUM of base + meters + options.
                        # PROBLEM: If we add "installation_price" above (line 154) AND add separate service links with prices, we double count?
                        # NO, "total_amount" is calculated on line 154.
                        # The "installation_services" list is used to create LINKS.
                        # The LINKS (OrderServiceLink) have a price.
                        # When calculate_totals() runs on the order later, it might sum up ServiceLinks + ProductLinks.
                        # Let's check calculate_totals in Order model... (I can't see it now, but assumingly it sums everything).
                        # BUT, line 143: link (ProductLink) has "installation_price".
                        # If we ALSO create ServiceLink, we double-charge.
                        
                        # ACTION: 
                        # 1. ProductLink should probably NOT store the full installation price if we are breaking it out into services.
                        # OR 
                        # 2. ProductLink stores it for "Product + Install" line item reference, but ServiceLinks are "extra"?
                        # The user wants them in "Services".
                        # Safest bet: Set ProductLink.installation_price to 0 or keeping it as "snapshot" but ensuring total calculation doesn't double dip.
                        # Actually, looking at line 149-154: `total_amount` is manually accumulated here.
                        # And `Order.total_amount` is set on line 247.
                        # So `calculate_totals` is NOT called here.
                        # So we are free to define links as we want for display.
                        
                        # RE-CALCULATION STRATEGY:
                        # 1. Main Install Price = Total Install Price (from payload) - Sum(Options Prices).
                        #    We need to fetch options to know their prices.
                        
                        from services.image_service import ImageService # Just in case, or use DAO
                        stmt_opts = select(Service).where(Service.slug.in_(options_slugs))
                        res_opts = await session.execute(stmt_opts)
                        db_options = res_opts.scalars().all()
                        
                        options_total_cost = 0
                        for opt in db_options:
                            options_total_cost += opt.base_price
                            # Add option as service link
                            installation_services.append({
                                "title": f"Доп. услуга: {opt.title}",
                                "price": opt.base_price,
                                "quantity": item["quantity"],
                                "service_id": opt.id # Link to actual service
                            })
                            
                        # Adjust Main Install Price in the Service Link to exclude options cost 
                        # so that Sum(Services) = Original Total Install Price
                        # (This assumes frontend passed the correct total).
                        
                        # Wait, the `installation_price` from payload is the Grand Total of valid install?
                        # Yes.
                        # So Main Link Price = PayloadPrice - OptionsCost.
                        
                        # Update the last added service (Main Install)
                        if installation_services:
                            # The main install is the one before options (index -1 - len(options))
                            # Actually we just added it.
                            main_svc_idx = len(installation_services) - 1 - len(db_options)
                            if main_svc_idx >= 0:
                                installation_services[main_svc_idx]["price"] -= options_total_cost
                    
                
                # Log details
                item_desc = f"{product.title} x{item['quantity']}"
                if with_installation:
                    item_desc += f" + монтаж ({installation_price} р.)"
                added_items.append(item_desc)

            elif product_id is None and item.get("with_installation"):
                # SERVICE-ONLY ORDER (Legacy/Calculator)
                # ... existing logic for service-only ...
                
                installation_price = int(item.get("installation_price", 0))
                meta = item.get("installation_meta", {})
                
                # ... (Same mapping logic as above) ...
                # Construct detailed title with friendly formatting
                type_raw = meta.get("type", "General")
                meters = meta.get("meters", 3)
                power_raw = meta.get("power_range", "")
                
                TYPE_MAP = {
                    'Wall': 'настенного типа',
                    'Настенный': 'настенного типа',
                    'Cassette': 'кассетного типа',
                    'Кассетный': 'кассетного типа',
                    'Ceiling': 'потолочного типа',
                    'Напольно-потолочный': 'потолочного типа',
                    'Duct': 'канального типа',
                    'Канальный': 'канального типа',
                    'Multisplit': 'мульти-сплит системы',
                    'Мульти-сплит': 'мульти-сплит системы'
                }
                
                POWER_MAP = {
                    'area-20, area-25, area-35': 'до 4 кВт',
                    'area-50, area-70': 'до 7 кВт',
                    'area-80, area-100': 'выше 7 кВт',
                    '07-12': 'до 3.5 кВт',
                    '18-24': 'до 7 кВт',
                    '30-36': 'выше 7 кВт'
                }
                
                type_str = TYPE_MAP.get(type_raw, type_raw)
                power_str = POWER_MAP.get(power_raw, power_raw)
                
                service_title = f"Монтаж кондиционера {type_str}"
                
                if power_str and power_str != "Standard":
                    if power_raw in POWER_MAP: 
                         service_title += f", мощностью {power_str}"
                    else:
                         found_power = False
                         for k, v in POWER_MAP.items():
                             if k in power_raw:
                                 service_title += f", мощностью {v}"
                                 found_power = True
                                 break
                         if not found_power:
                             service_title += f", мощностью {power_raw}"

                service_title += f", включая межблочную трассу {meters} м"
                # Add to total
                # Note: frontend usually passes the TOTAL meta price including options.
                # But here we will calculate options separately to link them properly.
                # To avoid double counting, we should SUBTRACT options cost from the "Main Install" price if the input `installation_price` included them.
                # However, for Calculator flow, we can assume we want to break it down.
                
                # Fetch detailed options if present
                options_slugs = item.get("installation_options", [])
                options_cost = 0
                service_links_to_add = []
                
                if options_slugs:
                    stmt_opts = select(Service).where(Service.slug.in_(options_slugs))
                    res_opts = await session.execute(stmt_opts)
                    db_options = res_opts.scalars().all()
                    
                    for opt in db_options:
                        options_cost += opt.base_price
                        service_links_to_add.append({
                            "title": f"Доп. опция: {opt.title}",
                            "price": opt.base_price,
                            "quantity": item["quantity"],
                            "service_id": opt.id
                        })

                # Calculate Main Install Price
                # If the incoming `installation_price` (total) includes options, we subtract them to get the base main install price.
                # This ensures: Main + Options = Total.
                main_install_price = installation_price - options_cost
                
                # Safety check: if main price goes negative (e.g. data mismatch), we keep it as is and just add extra services (assuming total was base).
                # But typically calculator sends Grand Total.
                if main_install_price < 0:
                     logger.warning(f"Main install price becoming negative ({main_install_price})! Assuming input price was base-only.")
                     main_install_price = installation_price
                     # In this case, total_amount will increase by options_cost
                     total_amount += options_cost * item["quantity"] # Add options on top
                
                # 1. Main Installation
                installation_services.append({
                    "title": service_title,
                    "price": main_install_price,
                    "quantity": item["quantity"]
                })
                
                # 2. Add Options
                installation_services.extend(service_links_to_add)
                
                # Add to total (Main + Options) or just original Total
                # Since we recalculated, sum(components) should equal original total if logic matches.
                # Let's trust the components we just built.
                # total_amount was initialized to 0 for this item scope? No, it's global accumulator.
                # We need to add THIS item's contribution.
                # Contribution = (Main + Sum(Options)) * Qty
                item_total = (main_install_price + options_cost) * item["quantity"]
                total_amount += item_total
                
                added_items.append(f"{service_title} x{item['quantity']} ({item_total} р.)")

            else:
                logger.warning(f"Product {product_id} not found/invalid in order creation")
        
        # 3b. Add installation services
        for inst_svc in installation_services:
            service_link = OrderServiceLink(
                order_id=order.id,
                proposal_id=proposal.id,
                service_id=inst_svc.get("service_id"), # Now supported
                title=inst_svc["title"],
                price=inst_svc["price"],
                quantity=inst_svc["quantity"]
            )
            session.add(service_link)
        
        # 4. Update totals and commit
        order.total_amount = total_amount
        await session.flush()
        await OrderService._refresh_order_financials(session, order)
        session.add(order)
        if commit:
            await session.commit()
            await session.refresh(order)
        else:
            await session.flush()
        
        # Log
        logger.info(
            "NEW_ORDER_CREATED order_id=%s source=%s item_count=%s total=%s installation_service_count=%s",
            order.id,
            lead_source.value,
            len(added_items),
            order.total_amount,
            len(installation_services),
        )
        logger.debug(f"Order #{order.id} items: {', '.join(added_items)}")
        
        return order

    @staticmethod
    async def update_order_links(session: AsyncSession, order_id: int, items_data: Dict[str, Any]) -> None:
        """
        Full sync of order items (products/services).
        Uses current DB prices for products.
        """
        order = await OrderDAO.get_with_links(session, order_id)
        if not order:
            return
        proposal = await OrderService.ensure_default_proposal(session, order)
        # 1. Очищаем старые связи
        await session.execute(delete(OrderProductLink).where(OrderProductLink.order_id == order_id, OrderProductLink.proposal_id == proposal.id))
        await session.execute(delete(OrderServiceLink).where(OrderServiceLink.order_id == order_id, OrderServiceLink.proposal_id == proposal.id))
        
        # 2. Добавляем товары
        for p in items_data.get("products", []):
            logistics_components = OrderService._serialize_order_logistics_components(
                p.get("logistics_components")
            )
            await OrderService._backfill_product_logistics_template(
                session,
                p.get("product_id"),
                logistics_components,
            )
            link = OrderProductLink(
                order_id=order_id,
                proposal_id=proposal.id,
                product_id=p["product_id"],
                quantity=p["quantity"],
                price=p["price"], # Цена должна приходить актуальная
                logistics_components=logistics_components,
            )
            session.add(link)
        
        # 3. Добавляем услуги
        for s in items_data.get("services", []):
            link = OrderServiceLink(
                order_id=order_id,
                proposal_id=proposal.id,
                service_id=s["service_id"],
                quantity=s["quantity"],
                price=s["price"]
            )
            session.add(link)
            
        # session.add_all(new_links) - Removed as items are added in loop
        await session.flush() # Ensure links are in DB

        # 4. Пересчитываем итоговые цифры заказа
        # Необходимо подгрузить связи, чтобы calculate_totals отработал корректно
        # Используем существующий метод DAO или подгружаем вручную
        await OrderService._refresh_order_financials(session, order)
        session.add(order)
            
        await session.commit()

    @staticmethod
    async def _ensure_assignable_legacy_executor(
        session: AsyncSession,
        installer_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> None:
        from models import Installer
        from services.staff_user_service import StaffUserService

        staff_user = await StaffUserService.get_by_legacy_installer_id(session, installer_id)
        if staff_user is not None:
            from services.staff_tenant_membership_service import (
                StaffTenantMembershipService,
            )

            membership = await StaffTenantMembershipService.get_for_tenant(
                session,
                tenant_id=tenant_scope.tenant_id,
                staff_user_id=int(staff_user.id or 0),
                active_only=True,
            )
            if (
                membership is None
                or not StaffUserService.can_be_any_executor(staff_user)
            ):
                raise ValueError("Selected installer is inactive or blocked")
            return

        if not tenant_scope.is_system:
            raise ValueError("Selected installer is not available for this tenant")
        installer = await session.get(Installer, installer_id)
        if not installer or not installer.is_active:
            raise ValueError("Selected installer is inactive or blocked")

    @staticmethod
    async def update_order_installers(
        session: AsyncSession,
        order_id: int,
        installers_data: List[Dict[str, Any]],
        *,
        tenant_scope: TenantScope,
    ) -> None:
        """
        Updates installers for an order and triggers notifications for NEW assignments.
        """
        from models import OrderInstaller, Installer
        from services.bot_service import BotService
        from services.staff_user_service import StaffUserService

        owned_order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if owned_order is None:
            raise ValueError("Order not found")
        
        # 1. Забираем текущие назначения чтобы понять, кто новый
        existing = await session.execute(select(OrderInstaller).where(OrderInstaller.order_id == order_id))
        existing_map = {i.installer_id: i for i in existing.scalars().all()}
        
        # 2. Очищаем старые (или обновляем, но для простоты пересоздадим)
        # В идеале нужно делать diff, но пока просто удалим те, кого нет в новом списке
        # Хотя для уведомлений нужно знать именно добавленных.
        
        new_installer_ids = {int(i['installer_id']) for i in installers_data}
        
        # Удаляем тех, кого нет в новом списке
        for i_id, link in list(existing_map.items()):
            if i_id not in new_installer_ids:
                await session.delete(link)
        
        # 3. Добавляем/Обновляем
        added_installers = []
        for i_data in installers_data:
            i_id = int(i_data['installer_id'])
            if i_id not in existing_map:
                await OrderService._ensure_assignable_legacy_executor(
                    session,
                    i_id,
                    tenant_scope=tenant_scope,
                )
                # Это новый!
                item = OrderInstaller(
                    order_id=order_id,
                    installer_id=i_id,
                    role=i_data.get('role', 'main'),
                    agreed_pay=float(i_data.get('agreed_pay', 0))
                )
                session.add(item)
                added_installers.append(i_id)
            else:
                # Обновляем существующего
                existing_item = existing_map[i_id]
                existing_item.agreed_pay = float(i_data.get('agreed_pay', 0))
                existing_item.role = i_data.get('role', 'main')
                session.add(existing_item)
        
        await session.flush()
        
        # 4. Триггер уведомлений для НОВЫХ
        if added_installers:
            # Подгружаем детали для сообщения
            order = await OrderDAO.get_with_links(session, order_id)
            # Подгружаем самих монтажников чтобы узнать telegram_id
            res = await session.execute(select(Installer).where(Installer.id.in_(added_installers)))
            installers_to_notify = res.scalars().all()
            
            for inst in installers_to_notify:
                telegram_id = await StaffUserService.get_active_executor_telegram_id_for_legacy_installer(
                    session,
                    inst,
                )
                if telegram_id:
                    delivered = await BotService.notify_installer_new_order(
                        installer_tg_id=telegram_id,
                        order_id=order_id,
                        address=order.delivery_address or "Адрес не указан",
                        date_str=order.installation_date.strftime("%d.%m.%Y") if order.installation_date else "Не назначена",
                        role="Монтажник" # Можно уточнить из связи
                    )
                    if not delivered:
                        logger.warning(
                            "INSTALLER_ORDER_NOTIFY_DELIVERY_FAILED order_id=%s installer_id=%s telegram_id=%s",
                            order_id,
                            inst.id,
                            telegram_id,
                        )

        # Пересчет
        order = await OrderDAO.get_with_links(session, order_id)
        if order:
            order.calculate_totals()
            session.add(order)
            
        await session.commit()

    @staticmethod
    async def update_all_items(
        session: AsyncSession, 
        order_id: int, 
        items_data: Dict[str, Any],
        *,
        tenant_scope: TenantScope,
    ) -> None:
        """
        Full sync of order items including products, services, and installers.
        Used by admin panel for order editing.
        
        Args:
            session: Database session
            order_id: Order ID
            items_data: Dict with 'products', 'services', 'installers' lists
        """
        from models import OrderInstaller
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
            options=(
                selectinload(Order.proposals),
                selectinload(Order.product_links),
                selectinload(Order.service_links),
                selectinload(Order.payments),
                selectinload(Order.installers),
            ),
            for_update=True,
        )
        if not order:
            return
        proposal = await OrderService.ensure_default_proposal(session, order)
        
        # 1. Clear existing links
        await session.execute(delete(OrderProductLink).where(OrderProductLink.order_id == order_id, OrderProductLink.proposal_id == proposal.id))
        await session.execute(delete(OrderServiceLink).where(OrderServiceLink.order_id == order_id, OrderServiceLink.proposal_id == proposal.id))
        
        # Clear installers
        stmt = OrderInstaller.__table__.delete().where(OrderInstaller.order_id == order_id)
        await session.execute(stmt)
        
        # 2. Add products
        for prod in items_data.get("products", []):
            logistics_components = OrderService._serialize_order_logistics_components(
                prod.get("logistics_components")
            )
            await OrderService._backfill_product_logistics_template(
                session,
                int(prod["product_id"]),
                logistics_components,
            )
            link = OrderProductLink(
                order_id=order_id,
                proposal_id=proposal.id,
                product_id=int(prod["product_id"]),
                quantity=int(prod["quantity"]),
                price=int(prod["price"]),
                logistics_components=logistics_components,
            )
            session.add(link)
        
        # 3. Add services (with custom titles)
        for serv in items_data.get("services", []):
            # Use None instead of 0 for service_id to enable snapshot pricing
            service_id_raw = serv.get("service_id", 0)
            service_id = None if (service_id_raw == 0 or service_id_raw is None) else int(service_id_raw)
            
            link = OrderServiceLink(
                order_id=order_id,
                proposal_id=proposal.id,
                service_id=service_id,  # Can be None for custom services
                title=serv.get("title"),  # Custom editable title
                quantity=int(serv["quantity"]),
                price=int(serv["price"])
            )
            session.add(link)
        
        # 4. Add installers
        for inst in items_data.get("installers", []):
            await OrderService._ensure_assignable_legacy_executor(
                session,
                int(inst["installer_id"]),
                tenant_scope=tenant_scope,
            )
            new_inst = OrderInstaller(
                order_id=order_id,
                installer_id=int(inst["installer_id"]),
                agreed_pay=int(inst.get("agreed_pay", 0)),
                role=inst.get("role", "main")
            )
            session.add(new_inst)
        
        await session.flush()
        
        # 5. Recalculate totals
        await OrderService._refresh_order_financials(session, order)
        session.add(order)
        
        await session.commit()

    @staticmethod
    async def check_stock_for_proposal(
        session: AsyncSession, 
        product_ids: List[int],
        min_stock: int = 3
    ) -> List[str]:
        """
        Check if products have sufficient stock for sending a proposal.
        
        Args:
            session: Database session
            product_ids: List of product IDs to check
            min_stock: Minimum required stock (default 3)
            
        Returns:
            List of warning strings for low-stock items. Empty if all OK.
        """
        if not product_ids:
            return []
        
        stmt = select(Product).where(Product.id.in_(product_ids))
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        low_stock_items = []
        for p in products:
            stock = getattr(p, 'stock_quantity', 0) or 0
            if stock < min_stock:
                low_stock_items.append(f"{p.title} ({stock})")
        
        return low_stock_items
    
    @staticmethod
    async def get_all_orders(session: AsyncSession) -> List[Order]:
        return await OrderDAO.get_all(session)

    @staticmethod
    async def add_order_stage(
        session: AsyncSession,
        order_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ):
        """Compatibility delegate to the transactional work-stage command."""
        from services.order_work_stage_command_service import OrderWorkStageCommandService

        return await OrderWorkStageCommandService.add_order_stage(
            session,
            order_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    def _map_stale_order_stage(stage: OrderWorkStage) -> Dict[str, Any]:
        order = getattr(stage, "order", None)
        customer = getattr(order, "customer", None) if order else None
        installer = getattr(stage, "installer", None)
        return {
            "id": stage.id,
            "order_id": stage.order_id,
            "order_status": order.status.value if order and hasattr(order.status, "value") else str(order.status if order else ""),
            "order_title": OrderService._display_order_title(order) if order else None,
            "name": stage.name,
            "status": stage.status.value if hasattr(stage.status, "value") else str(stage.status),
            "start_time": stage.start_time,
            "end_time": stage.end_time,
            "installer_id": stage.installer_id,
            "installer_name": installer.name if installer else None,
            "customer_name": customer.name if customer else None,
            "customer_phone": customer.phone if customer else None,
            "address": order.delivery_address if order else None,
            "manager_comment": stage.manager_comment,
            "installer_report": stage.installer_report,
        }

    @staticmethod
    async def list_stale_order_stages(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        older_than_days: int = 7,
        include_unscheduled: bool = True,
        limit: int = 100,
    ) -> Dict[str, Any]:
        safe_limit = max(1, min(int(limit or 100), 100))
        cutoff = datetime.now() - timedelta(days=max(0, int(older_than_days or 0)))
        stale_conditions = [OrderWorkStage.start_time < cutoff]
        if include_unscheduled:
            stale_conditions.append(OrderWorkStage.start_time.is_(None))

        base_filters = [
            TenantEntityAccessService.order_clause(tenant_scope),
            TenantEntityAccessService.order_customer_clause(tenant_scope),
            OrderWorkStage.status.notin_([OrderStageStatus.COMPLETED, OrderStageStatus.CANCELED]),
            or_(*stale_conditions),
        ]
        count_result = await session.execute(
            select(func.count())
            .select_from(OrderWorkStage)
            .join(Order, Order.id == OrderWorkStage.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(*base_filters)
        )
        total = int(count_result.scalar_one() or 0)

        result = await session.execute(
            select(OrderWorkStage)
            .join(Order, Order.id == OrderWorkStage.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(*base_filters)
            .options(
                selectinload(OrderWorkStage.order).selectinload(Order.customer),
                selectinload(OrderWorkStage.installer),
            )
            .order_by(OrderWorkStage.start_time.asc().nullsfirst(), OrderWorkStage.id.asc())
            .limit(safe_limit)
        )
        return {
            "items": [OrderService._map_stale_order_stage(stage) for stage in result.scalars().all()],
            "total": total,
        }

    @staticmethod
    async def cancel_order_stage_direct(
        session: AsyncSession,
        stage_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        """Compatibility delegate to the transactional work-stage command."""
        from services.order_work_stage_command_service import OrderWorkStageCommandService

        return await OrderWorkStageCommandService.cancel_order_stage_direct(
            session,
            stage_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def delete_order_stage_direct(
        session: AsyncSession,
        stage_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        """Compatibility delegate to the transactional work-stage command."""
        from services.order_work_stage_command_service import OrderWorkStageCommandService

        return await OrderWorkStageCommandService.delete_order_stage_direct(
            session,
            stage_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def update_order_stage(
        session: AsyncSession,
        order_id: int,
        stage_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ):
        """Compatibility delegate to the transactional work-stage command."""
        from services.order_work_stage_command_service import OrderWorkStageCommandService

        return await OrderWorkStageCommandService.update_order_stage(
            session,
            order_id,
            stage_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def delete_order_stage(
        session: AsyncSession,
        order_id: int,
        stage_id: int,
        *,
        tenant_scope: TenantScope,
    ):
        """Compatibility delegate to the transactional work-stage command."""
        from services.order_work_stage_command_service import OrderWorkStageCommandService

        return await OrderWorkStageCommandService.delete_order_stage(
            session,
            order_id,
            stage_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def update_status(session: AsyncSession, order_id: int, new_status: Any) -> bool:
        """Update order status."""
        return await OrderDAO.update_status(session, order_id, new_status)

    @staticmethod
    async def update_status_from_admin(
        session: AsyncSession,
        order_id: int,
        new_status: str,
    ) -> Dict[str, Any]:
        try:
            status_enum = OrderStatus(new_status)
        except ValueError:
            return {"success": False, "error": f"Invalid status: {new_status}"}

        try:
            success = await OrderService.update_status(session, order_id, status_enum)
            return {"success": success}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @staticmethod
    async def get_orders_for_manager(
        session: AsyncSession,
        customer_segment: str,
        page: int,
        limit: int,
        *,
        tenant_scope: TenantScope,
        status: Optional[str] = None,
        search: Optional[str] = None,
        overdue_only: bool = False,
        sort: str = "created_at_desc",
    ) -> Dict[str, Any]:
        """Compatibility delegate to the Manager order read model."""
        from services.order_projection_service import OrderProjectionService

        return await OrderProjectionService.get_orders_for_manager(
            session=session,
            customer_segment=customer_segment,
            page=page,
            limit=limit,
            tenant_scope=tenant_scope,
            status=status,
            search=search,
            overdue_only=overdue_only,
            sort=sort,
        )

    @staticmethod
    async def get_order_detail_for_manager(
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility delegate to the Manager order read model."""
        from services.order_projection_service import OrderProjectionService

        return await OrderProjectionService.get_order_detail_for_manager(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def create_order_proposal(
        session: AsyncSession,
        order_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        """Compatibility delegate to the transactional proposal command."""
        from services.order_proposal_command_service import OrderProposalCommandService

        return await OrderProposalCommandService.create_order_proposal(
            session,
            order_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def update_order_proposal(
        session: AsyncSession,
        order_id: int,
        proposal_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        """Compatibility delegate to the transactional proposal command."""
        from services.order_proposal_command_service import OrderProposalCommandService

        return await OrderProposalCommandService.update_order_proposal(
            session,
            order_id,
            proposal_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def select_order_proposal(
        session: AsyncSession,
        order_id: int,
        proposal_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        """Compatibility delegate to the transactional proposal command."""
        from services.order_proposal_command_service import OrderProposalCommandService

        return await OrderProposalCommandService.select_order_proposal(
            session,
            order_id,
            proposal_id,
            tenant_scope=tenant_scope,
        )


    @staticmethod
    async def build_manager_order_line_defaults(
        session: AsyncSession,
        product_id: Optional[int] = None,
        service_id: Optional[int] = None,
    ) -> Dict[str, int]:
        if product_id is not None:
            product = await session.get(Product, product_id)
            return {"cost": int(getattr(product, "cost", 0) or 0)} if product else {"cost": 0}
        if service_id is not None:
            service = await session.get(Service, service_id)
            return {"cost": int(getattr(service, "base_price", 0) or 0)} if service else {"cost": 0}
        return {"cost": 0}

    @staticmethod
    async def _build_product_line_cost_defaults(session: AsyncSession, product_lines: List[Any]) -> Dict[int, int]:
        _ = session
        return {
            product_id: 0
            for product_id in {
                int(line.product_id)
                for line in product_lines
                if getattr(line, "cost", None) is None and getattr(line, "product_id", None) is not None
            }
        }

    @staticmethod
    async def _build_service_line_cost_defaults(session: AsyncSession, service_lines: List[Any]) -> Dict[int, int]:
        service_ids = {
            int(line.service_id)
            for line in service_lines
            if getattr(line, "cost", None) is None and getattr(line, "service_id", None) is not None
        }
        if not service_ids:
            return {}
        result = await session.execute(select(Service.id, Service.base_price).where(Service.id.in_(service_ids)))
        return {int(service_id): int(base_price or 0) for service_id, base_price in result.all()}

    @staticmethod
    async def _maybe_add_default_repair_diagnostic(session: AsyncSession, order: Order) -> None:
        await session.refresh(order, attribute_names=["proposals", "service_links", "payments", "product_links", "installers"])
        selected_proposal = await OrderService.ensure_default_proposal(session, order)
        target_proposal_id = int(selected_proposal.id)
        existing_services = [
            link for link in order.service_links
            if link.proposal_id == target_proposal_id
        ]
        if any("диагност" in (link.title or "").lower() for link in existing_services):
            return

        result = await session.execute(
            select(ServiceTariff)
            .where(
                ServiceTariff.service_kind == "repair",
                ServiceTariff.is_active == True,  # noqa: E712
                or_(
                    ServiceTariff.short_name.ilike("%диагност%"),
                    ServiceTariff.selector_label.ilike("%диагност%"),
                ),
            )
            .order_by(ServiceTariff.sort_order, ServiceTariff.id)
            .limit(1)
        )
        tariff = result.scalars().first()
        if not tariff:
            return

        session.add(
            OrderServiceLink(
                order_id=int(order.id),
                proposal_id=target_proposal_id,
                service_id=None,
                title=OrderService._clean_order_title(tariff.effective_short_name) or tariff.effective_short_name,
                quantity=1,
                price=int(tariff.base_price or 0),
                cost=0,
            )
        )
        await session.flush()
        await OrderService._refresh_order_financials(session, order)

    @staticmethod
    async def update_order_for_manager(
        session: AsyncSession,
        order_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility delegate to the transactional update command."""
        from services.order_update.command import OrderUpdateCommandService

        return await OrderUpdateCommandService.update_order_for_manager(
            session,
            order_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def add_payment(
        session: AsyncSession,
        order_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ):
        """Compatibility delegate to the transactional payment command."""
        from services.order_payment_command_service import OrderPaymentCommandService

        return await OrderPaymentCommandService.add_payment(
            session,
            order_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def delete_payment(
        session: AsyncSession,
        order_id: int,
        payment_id: int,
        *,
        tenant_scope: TenantScope,
    ):
        """Compatibility delegate to the transactional payment command."""
        from services.order_payment_command_service import OrderPaymentCommandService

        return await OrderPaymentCommandService.delete_payment(
            session,
            order_id,
            payment_id,
            tenant_scope=tenant_scope,
        )

    # -----------------------------------------------------------------
    # Leads Inbox (Order-based triage)
    # -----------------------------------------------------------------

    @staticmethod
    async def get_new_lead_counter(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> tuple[int, bool]:
        """Fast count of orders with status 'new_lead'.

        Intended for the Dashboard/Sidebar badge — runs a single
        indexed COUNT query with no joins.
        """
        stmt = (
            select(func.count())
            .select_from(Order)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                Order.status == OrderStatus.NEW_LEAD,
                TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
            )
        )
        result = await session.execute(stmt)
        count: int = result.scalar() or 0
        return count, count > 0

    @staticmethod
    def _parse_lead_inbox_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None) if value.tzinfo else value
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed

    @staticmethod
    def _extract_email_source_created_at(order: Order) -> Optional[datetime]:
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        parsed = OrderService._parse_lead_inbox_datetime(meta.get("email_date"))
        if parsed:
            return parsed

        marker = "Дата письма:"
        comment = order.comment or ""
        marker_index = comment.find(marker)
        if marker_index < 0:
            return None
        raw_line = comment[marker_index + len(marker):].strip().splitlines()[0].strip()
        return OrderService._parse_lead_inbox_datetime(raw_line)

    @staticmethod
    def _lead_inbox_customer_type(order: Order) -> Optional[str]:
        customer = order.customer
        if not customer:
            return None

        customer_type = customer.type.value if hasattr(customer.type, "value") else str(customer.type or "")
        if customer_type == "company" or customer.inn or customer.full_legal_name:
            return "company"

        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        raw_meta_type = str(meta.get("lead_customer_type") or "").strip()
        if raw_meta_type == "company":
            return "company"
        if raw_meta_type == "individual" and meta.get("lead_customer_type_known") is True:
            return "individual"
        if meta.get("lead_customer_type_known") is True and customer_type == "individual":
            return "individual"

        return None

    @staticmethod
    def _lead_inbox_meta_text(order: Order, key: str) -> Optional[str]:
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        value = meta.get(key)
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    async def get_leads_inbox(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        scope: str = "active",
        page: int = 1,
        limit: int = 50,
    ):
        """Return triage inbox items based on scope.

        scope="active"  → new_lead + assessment
                          sorted: new_lead first, then by created_at DESC.
        scope="archive" → canceled only, created_at DESC.
        """
        from schemas import LeadsInboxItemResponse, LeadsInboxListResponse, Meta
        from sqlalchemy import case as sa_case

        page = max(1, int(page or 1))
        limit = min(100, max(1, int(limit or 50)))
        ownership_clause = TenantEntityAccessService.order_clause(tenant_scope)
        customer_ownership_clause = or_(
            Order.customer_id.is_(None),
            tenant_scope_clause(Customer, tenant_scope),
        )
        stmt = (
            select(Order)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(ownership_clause, customer_ownership_clause)
            .options(selectinload(Order.customer))
        )
        count_stmt = (
            select(func.count(Order.id))
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(ownership_clause, customer_ownership_clause)
        )

        if scope == "archive":
            # Archived leads are just closed/lost leads
            scope_filters = (
                Order.status == OrderStatus.CLOSED,
                Order.closing_result == "lost"
            )
        else:
            active_statuses = [OrderStatus.NEW_LEAD]
            scope_filters = (Order.status.in_(active_statuses),)

        stmt = stmt.where(*scope_filters)
        count_stmt = count_stmt.where(*scope_filters)

        if scope == "active":
            # new_lead orders float to top, then newest first
            priority_expr = sa_case(
                (Order.status == OrderStatus.NEW_LEAD, 0),
                else_=1,
            )
            stmt = stmt.order_by(priority_expr, Order.created_at.desc())
        else:
            stmt = stmt.order_by(Order.created_at.desc())

        total_result = await session.execute(count_stmt)
        total = int(total_result.scalar() or 0)

        stmt = stmt.offset((page - 1) * limit).limit(limit)
        result = await session.execute(stmt)
        orders: list[Order] = list(result.scalars().all())
        from services.service_attachment_service import ServiceAttachmentService

        attachment_counts = await ServiceAttachmentService.order_attachment_counts(
            session,
            order_ids=[int(order.id or 0) for order in orders],
            tenant_scope=tenant_scope,
        )

        items = [
            LeadsInboxItemResponse(
                id=order.id,
                status=order.status.value if hasattr(order.status, "value") else str(order.status),
                is_new=(
                    (order.status.value if hasattr(order.status, "value") else str(order.status))
                    == "new_lead"
                ),
                customer_id=order.customer_id,
                customer_name=order.customer.name if order.customer else None,
                phone=order.customer.phone if order.customer else None,
                email=order.customer.email if order.customer else None,
                source=(
                    order.lead_source.value
                    if order.lead_source and hasattr(order.lead_source, "value")
                    else (str(order.lead_source) if order.lead_source else None)
                ),
                comment=order.comment,
                no_answer_at=OrderService._parse_lead_inbox_datetime(
                    order.technical_meta.get("no_answer_at") if isinstance(order.technical_meta, dict) else None
                ),
                source_created_at=OrderService._extract_email_source_created_at(order),
                created_at=order.created_at,
                customer_type=OrderService._lead_inbox_customer_type(order),
                customer_inn=order.customer.inn if order.customer else None,
                customer_full_legal_name=order.customer.full_legal_name if order.customer else None,
                customer_delivery_address=order.delivery_address,
                object_type=OrderService._lead_inbox_meta_text(order, "object_type"),
                service_type=OrderService._lead_inbox_meta_text(order, "service_type"),
                equipment_class=OrderService._lead_inbox_meta_text(order, "equipment_class"),
                marketing_source=OrderService._lead_inbox_meta_text(order, "marketing_source"),
                attachment_count=attachment_counts.get(int(order.id or 0), 0),
            )
            for order in orders
        ]

        pages = (total + limit - 1) // limit if limit > 0 else 0
        return LeadsInboxListResponse(
            items=items,
            total=total,
            meta=Meta(total=total, page=page, limit=limit, pages=pages),
        )

    @staticmethod
    async def delete_order(
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> bool:
        """
        Delete an order and all cascading dependencies from DB.
        Google Drive files are deleted on a best-effort basis and do not block DB deletion.
        """
        import sqlalchemy as sa
        from models.order import (
            BankReceipt,
            Order,
            OrderDocument,
            OrderInstaller,
            OrderProductLink,
            OrderProposal,
            OrderServiceLink,
            OrderWorkStage,
            OutgoingEmail,
            Payment,
        )
        from services.document_service import DocumentService
        from services.google_service import get_google_service
        
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Delete associated documents from Google Drive (best-effort).
        # OrderDocument rows themselves are deleted by ORM cascade together with the order.
        docs = await DocumentService.list_order_documents(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        for doc in docs or []:
            if not doc.google_file_id:
                continue
            try:
                get_google_service().delete_file(doc.google_file_id)
            except Exception as exc:
                logger.warning(
                    "Failed to delete Google Drive file while deleting order",
                    extra={"order_id": order_id, "doc_id": doc.id, "google_file_id": doc.google_file_id, "error": str(exc)},
                )

        # Explicit SQL updates/deletes avoid async lazy-load cascade pitfalls on AsyncSession.
        # Keep audit/history rows, but detach them from an order that is being hard-deleted.
        await session.execute(
            sa.update(BankReceipt)
            .where(BankReceipt.matched_order_id == order_id)
            .values(
                status="requires_review",
                matched_order_id=None,
                matched_payment_id=None,
                match_meta={"reason": "matched_order_deleted", "deleted_order_id": order_id},
            )
        )
        await session.execute(
            sa.update(OutgoingEmail)
            .where(OutgoingEmail.order_id == order_id)
            .values(order_id=None)
        )
        await session.execute(sa.delete(OrderProductLink).where(OrderProductLink.order_id == order_id))
        await session.execute(sa.delete(OrderServiceLink).where(OrderServiceLink.order_id == order_id))
        await session.execute(sa.delete(OrderWorkStage).where(OrderWorkStage.order_id == order_id))
        await session.execute(sa.delete(OrderInstaller).where(OrderInstaller.order_id == order_id))
        await session.execute(sa.delete(Payment).where(Payment.order_id == order_id))
        await session.execute(sa.delete(OrderDocument).where(OrderDocument.order_id == order_id))
        await session.execute(sa.delete(OrderProposal).where(OrderProposal.order_id == order_id))
        await session.execute(sa.delete(Order).where(Order.id == order_id))
        await session.commit()
        
        return True
