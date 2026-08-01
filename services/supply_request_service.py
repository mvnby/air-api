from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.supply_request import SupplyRequestDAO
from models.order import OrderProductLink
from models.product import Product
from models.supplier import (
    ProductSupplierMapping,
    Supplier,
    SupplierContact,
    SupplierOffer,
    SupplierWarehouse,
    SupplyRequest,
    SupplyRequestLine,
)
from models.tenancy import TenantScope
from services.fx_rate_service import FxRateService
from services.product_supply_metrics_service import ProductSupplyMetricsService


VALID_PAYMENT_METHODS = {"cash", "bank", "mixed", "unknown"}
VALID_INTENTS = {"reserve", "order"}
VALID_REQUEST_STATUSES = {
    "draft",
    "awaiting_reply",
    "reserved",
    "ordered",
    "ready_for_pickup",
    "picked_up",
    "received",
    "canceled",
}
VALID_SOURCE_TYPES = {"order_line", "stock", "manual"}


def _clean_text(value: Any) -> str | None:
    cleaned = " ".join(str(value or "").split())
    return cleaned or None


def _clean_required(value: Any, field_name: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _payment_method(value: str | None, fallback: str | None = None) -> str:
    candidate = _clean_text(value) or _clean_text(fallback) or "unknown"
    return candidate if candidate in VALID_PAYMENT_METHODS else "unknown"


def _intent(value: str | None) -> str:
    candidate = _clean_text(value) or "order"
    if candidate not in VALID_INTENTS:
        raise ValueError("Invalid supply intent")
    return candidate


def _status(value: str | None) -> str:
    candidate = _clean_text(value) or "draft"
    if candidate not in VALID_REQUEST_STATUSES:
        raise ValueError("Invalid supply status")
    return candidate


def _source_type(value: str | None) -> str:
    candidate = _clean_text(value) or "manual"
    if candidate not in VALID_SOURCE_TYPES:
        raise ValueError("Invalid supply line source type")
    return candidate


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception as exc:
        raise ValueError("Invalid money value") from exc


def _line_cost_float(line: SupplyRequestLine) -> float | None:
    return float(line.unit_cost_snapshot) if line.unit_cost_snapshot is not None else None


class SupplierProfileService:
    @staticmethod
    async def list_contacts(session: AsyncSession, supplier_id: int) -> dict:
        await SupplierProfileService._require_supplier(session, supplier_id)
        result = await session.execute(
            select(SupplierContact)
            .where(SupplierContact.supplier_id == supplier_id)
            .order_by(
                SupplierContact.default_for_orders.desc(),
                SupplierContact.default_for_logistics.desc(),
                SupplierContact.name.asc(),
            )
        )
        return {"items": list(result.scalars().all())}

    @staticmethod
    async def create_contact(session: AsyncSession, supplier_id: int, payload: dict) -> SupplierContact:
        await SupplierProfileService._require_supplier(session, supplier_id)
        data = SupplierProfileService._normalize_contact_payload(payload)
        data["supplier_id"] = supplier_id
        await SupplierProfileService._clear_contact_defaults_if_needed(session, supplier_id, data)
        contact = SupplierContact(**data)
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact

    @staticmethod
    async def update_contact(
        session: AsyncSession,
        supplier_id: int,
        contact_id: int,
        payload: dict,
    ) -> SupplierContact | None:
        contact = await session.get(SupplierContact, contact_id)
        if not contact or contact.supplier_id != supplier_id:
            return None
        data = SupplierProfileService._normalize_contact_payload(payload, partial=True)
        await SupplierProfileService._clear_contact_defaults_if_needed(session, supplier_id, data, exclude_id=contact_id)
        for key, value in data.items():
            setattr(contact, key, value)
        contact.updated_at = datetime.now()
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact

    @staticmethod
    async def delete_contact(session: AsyncSession, supplier_id: int, contact_id: int) -> bool:
        contact = await session.get(SupplierContact, contact_id)
        if not contact or contact.supplier_id != supplier_id:
            return False
        warehouse_result = await session.execute(
            select(SupplierWarehouse).where(SupplierWarehouse.contact_id == contact_id)
        )
        for warehouse in warehouse_result.scalars().all():
            warehouse.contact_id = None
            session.add(warehouse)
        request_result = await session.execute(
            select(SupplyRequest).where(
                or_(
                    SupplyRequest.supplier_contact_id == contact_id,
                    SupplyRequest.logistics_contact_id == contact_id,
                )
            )
        )
        for request in request_result.scalars().all():
            if request.supplier_contact_id == contact_id:
                request.supplier_contact_id = None
            if request.logistics_contact_id == contact_id:
                request.logistics_contact_id = None
            session.add(request)
        await session.delete(contact)
        await session.commit()
        return True

    @staticmethod
    async def list_warehouses(session: AsyncSession, supplier_id: int) -> dict:
        await SupplierProfileService._require_supplier(session, supplier_id)
        result = await session.execute(
            select(SupplierWarehouse)
            .where(SupplierWarehouse.supplier_id == supplier_id)
            .order_by(SupplierWarehouse.is_default.desc(), SupplierWarehouse.name.asc())
        )
        return {"items": list(result.scalars().all())}

    @staticmethod
    async def create_warehouse(session: AsyncSession, supplier_id: int, payload: dict) -> SupplierWarehouse:
        await SupplierProfileService._require_supplier(session, supplier_id)
        data = SupplierProfileService._normalize_warehouse_payload(payload)
        data["supplier_id"] = supplier_id
        await SupplierProfileService._validate_contact_belongs_to_supplier(session, supplier_id, data.get("contact_id"))
        await SupplierProfileService._clear_warehouse_default_if_needed(session, supplier_id, data)
        warehouse = SupplierWarehouse(**data)
        session.add(warehouse)
        await session.commit()
        await session.refresh(warehouse)
        return warehouse

    @staticmethod
    async def update_warehouse(
        session: AsyncSession,
        supplier_id: int,
        warehouse_id: int,
        payload: dict,
    ) -> SupplierWarehouse | None:
        warehouse = await session.get(SupplierWarehouse, warehouse_id)
        if not warehouse or warehouse.supplier_id != supplier_id:
            return None
        data = SupplierProfileService._normalize_warehouse_payload(payload, partial=True)
        await SupplierProfileService._validate_contact_belongs_to_supplier(session, supplier_id, data.get("contact_id"))
        await SupplierProfileService._clear_warehouse_default_if_needed(session, supplier_id, data, exclude_id=warehouse_id)
        for key, value in data.items():
            setattr(warehouse, key, value)
        warehouse.updated_at = datetime.now()
        session.add(warehouse)
        await session.commit()
        await session.refresh(warehouse)
        return warehouse

    @staticmethod
    async def delete_warehouse(session: AsyncSession, supplier_id: int, warehouse_id: int) -> bool:
        warehouse = await session.get(SupplierWarehouse, warehouse_id)
        if not warehouse or warehouse.supplier_id != supplier_id:
            return False
        request_result = await session.execute(
            select(SupplyRequest).where(SupplyRequest.warehouse_id == warehouse_id)
        )
        for request in request_result.scalars().all():
            request.warehouse_id = None
            session.add(request)
        await session.delete(warehouse)
        await session.commit()
        return True

    @staticmethod
    async def _require_supplier(session: AsyncSession, supplier_id: int) -> Supplier:
        supplier = await session.get(Supplier, supplier_id)
        if not supplier:
            raise ValueError("Supplier not found")
        return supplier

    @staticmethod
    def _normalize_contact_payload(payload: dict, partial: bool = False) -> dict:
        data = dict(payload)
        if "name" in data or not partial:
            data["name"] = _clean_required(data.get("name"), "Contact name")
        for key in ("role", "phone", "viber", "telegram_username", "telegram_chat_id", "email", "comment"):
            if key in data:
                data[key] = _clean_text(data.get(key))
        if "preferred_channel" in data or not partial:
            channel = _clean_text(data.get("preferred_channel")) or "phone"
            data["preferred_channel"] = channel if channel in {"phone", "viber", "telegram", "email", "other"} else "phone"
        return data

    @staticmethod
    def _normalize_warehouse_payload(payload: dict, partial: bool = False) -> dict:
        data = dict(payload)
        if "name" in data or not partial:
            data["name"] = _clean_required(data.get("name"), "Warehouse name")
        if "address" in data or not partial:
            data["address"] = _clean_required(data.get("address"), "Warehouse address")
        for key in ("contact_name", "contact_phone", "work_hours", "pickup_notes"):
            if key in data:
                data[key] = _clean_text(data.get(key))
        return data

    @staticmethod
    async def _validate_contact_belongs_to_supplier(
        session: AsyncSession,
        supplier_id: int,
        contact_id: int | None,
    ) -> None:
        if not contact_id:
            return
        contact = await session.get(SupplierContact, contact_id)
        if not contact or contact.supplier_id != supplier_id:
            raise ValueError("Supplier contact not found")

    @staticmethod
    async def _clear_contact_defaults_if_needed(
        session: AsyncSession,
        supplier_id: int,
        payload: dict,
        exclude_id: int | None = None,
    ) -> None:
        for flag in ("default_for_orders", "default_for_logistics"):
            if payload.get(flag) is not True:
                continue
            stmt = select(SupplierContact).where(
                SupplierContact.supplier_id == supplier_id,
                getattr(SupplierContact, flag).is_(True),
            )
            if exclude_id:
                stmt = stmt.where(SupplierContact.id != exclude_id)
            result = await session.execute(stmt)
            for contact in result.scalars().all():
                setattr(contact, flag, False)
                session.add(contact)

    @staticmethod
    async def _clear_warehouse_default_if_needed(
        session: AsyncSession,
        supplier_id: int,
        payload: dict,
        exclude_id: int | None = None,
    ) -> None:
        if payload.get("is_default") is not True:
            return
        stmt = select(SupplierWarehouse).where(
            SupplierWarehouse.supplier_id == supplier_id,
            SupplierWarehouse.is_default.is_(True),
        )
        if exclude_id:
            stmt = stmt.where(SupplierWarehouse.id != exclude_id)
        result = await session.execute(stmt)
        for warehouse in result.scalars().all():
            warehouse.is_default = False
            session.add(warehouse)


class SupplyRequestService:
    @staticmethod
    async def list_requests(
        session: AsyncSession,
        *,
        page: int = 1,
        limit: int = 50,
        status: str | None = None,
        supplier_id: int | None = None,
        warehouse_id: int | None = None,
        source_type: str | None = None,
        order_id: int | None = None,
    ) -> dict:
        page = max(1, page)
        limit = min(max(1, limit), 100)
        stmt = select(SupplyRequest)
        count_stmt = select(func.count(SupplyRequest.id))
        filters = []
        if status:
            filters.append(SupplyRequest.status == _status(status))
        if supplier_id:
            filters.append(SupplyRequest.supplier_id == supplier_id)
        if warehouse_id:
            filters.append(SupplyRequest.warehouse_id == warehouse_id)
        if source_type or order_id:
            count_stmt = select(func.count(func.distinct(SupplyRequest.id)))
            stmt = stmt.join(SupplyRequestLine)
            count_stmt = count_stmt.join(SupplyRequestLine)
            if source_type:
                filters.append(SupplyRequestLine.source_type == _source_type(source_type))
            if order_id:
                stmt = stmt.join(OrderProductLink, SupplyRequestLine.order_product_link_id == OrderProductLink.id)
                count_stmt = count_stmt.join(OrderProductLink, SupplyRequestLine.order_product_link_id == OrderProductLink.id)
                filters.append(OrderProductLink.order_id == order_id)
        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)
        stmt = (
            stmt.distinct()
            .options(
                selectinload(SupplyRequest.supplier),
                selectinload(SupplyRequest.warehouse),
                selectinload(SupplyRequest.supplier_contact),
                selectinload(SupplyRequest.logistics_contact),
                selectinload(SupplyRequest.lines).selectinload(SupplyRequestLine.product),
            )
            .order_by(SupplyRequest.updated_at.desc(), SupplyRequest.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        result = await session.execute(stmt)
        items = [SupplyRequestService._serialize_request(item) for item in result.scalars().all()]
        return {
            "items": items,
            "meta": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if limit else 1,
            },
        }

    @staticmethod
    async def create_request(session: AsyncSession, payload: dict, *, created_by: str | None = None) -> dict:
        supplier = await SupplierProfileService._require_supplier(session, int(payload["supplier_id"]))
        intent = _intent(payload.get("intent"))
        payment_method = _payment_method(payload.get("payment_method"), supplier.default_payment_method)
        warehouse = await SupplyRequestService._resolve_warehouse(session, supplier.id, payload.get("warehouse_id"))
        supplier_contact = await SupplyRequestService._resolve_contact(
            session,
            supplier.id,
            payload.get("supplier_contact_id"),
            default_flag="default_for_orders",
        )
        logistics_contact = await SupplyRequestService._resolve_contact(
            session,
            supplier.id,
            payload.get("logistics_contact_id"),
            default_flag="default_for_logistics",
        )
        request = SupplyRequest(
            supplier_id=supplier.id,
            warehouse_id=warehouse.id if warehouse else None,
            supplier_contact_id=supplier_contact.id if supplier_contact else None,
            logistics_contact_id=logistics_contact.id if logistics_contact else None,
            intent=intent,
            payment_method=payment_method,
            comment=_clean_text(payload.get("comment")),
            created_by=created_by,
        )
        session.add(request)
        await session.flush()

        for raw_line in payload.get("lines") or []:
            line = await SupplyRequestService._build_manual_line(session, raw_line, request.id)
            session.add(line)
        await session.commit()
        return {"items": [await SupplyRequestService.get_request(session, request.id)]}

    @staticmethod
    async def create_from_order_lines(
        session: AsyncSession,
        payload: dict,
        *,
        tenant_scope: TenantScope,
        created_by: str | None = None,
    ) -> dict:
        line_ids = [int(value) for value in payload.get("order_product_link_ids") or []]
        if not line_ids:
            raise ValueError("Order product lines are required")
        links = await SupplyRequestDAO.get_order_product_links_for_storefront(
            session,
            order_product_link_ids=line_ids,
            tenant_scope=tenant_scope,
        )
        if len(links) != len(set(line_ids)):
            raise ValueError("Some order product lines were not found")

        grouped: dict[tuple[int, int | None, str, str], list[SupplyRequestLine]] = defaultdict(list)
        request_meta: dict[tuple[int, int | None, str, str], dict[str, Any]] = {}
        intent = _intent(payload.get("intent"))
        for link in links:
            if not link.product_id:
                raise ValueError("Order product line is not linked to catalog product")
            offer = await SupplyRequestService._select_default_offer(
                session,
                int(link.product_id),
                supplier_id=payload.get("supplier_id"),
            )
            supplier_id = int(payload["supplier_id"]) if payload.get("supplier_id") else int(offer.supplier_id) if offer else None
            if not supplier_id:
                raise ValueError(f"No supplier mapping for product line #{link.id}")
            supplier = await SupplierProfileService._require_supplier(session, supplier_id)
            warehouse = await SupplyRequestService._resolve_warehouse(session, supplier_id, payload.get("warehouse_id"))
            payment_method = _payment_method(payload.get("payment_method"), supplier.default_payment_method)
            key = (supplier_id, warehouse.id if warehouse else None, payment_method, intent)
            request_meta[key] = {
                "supplier": supplier,
                "warehouse": warehouse,
                "payment_method": payment_method,
                "intent": intent,
                "comment": _clean_text(payload.get("comment")),
            }
            line = SupplyRequestLine(
                request_id=0,
                order_product_link_id=link.id,
                source_type="order_line",
                product_id=link.product_id,
                supplier_offer_external_id=offer.external_id if offer else None,
                supplier_offer_title=offer.title_raw if offer else None,
                title_snapshot=link.product.title if link.product else f"Товар #{link.product_id}",
                qty=max(1, int(link.quantity or 1)),
                unit_cost_snapshot=await SupplyRequestService._offer_cost_decimal(session, offer) if offer else _decimal_or_none(link.cost),
                status="draft",
            )
            grouped[key].append(line)

        requests = []
        for key, lines in grouped.items():
            meta = request_meta[key]
            supplier = meta["supplier"]
            warehouse = meta["warehouse"]
            supplier_contact = await SupplyRequestService._resolve_contact(
                session, supplier.id, None, default_flag="default_for_orders"
            )
            logistics_contact = await SupplyRequestService._resolve_contact(
                session, supplier.id, None, default_flag="default_for_logistics"
            )
            request = SupplyRequest(
                supplier_id=supplier.id,
                warehouse_id=warehouse.id if warehouse else None,
                supplier_contact_id=supplier_contact.id if supplier_contact else None,
                logistics_contact_id=logistics_contact.id if logistics_contact else None,
                intent=meta["intent"],
                payment_method=meta["payment_method"],
                comment=meta["comment"],
                created_by=created_by,
            )
            session.add(request)
            await session.flush()
            for line in lines:
                line.request_id = request.id
                session.add(line)
            requests.append(request)
        await session.commit()
        return {"items": [await SupplyRequestService.get_request(session, int(request.id)) for request in requests if request.id]}

    @staticmethod
    async def create_stock_requests(session: AsyncSession, payload: dict, *, created_by: str | None = None) -> dict:
        intent = _intent(payload.get("intent"))
        grouped: dict[tuple[int, int | None, str, str], list[SupplyRequestLine]] = defaultdict(list)
        request_meta: dict[tuple[int, int | None, str, str], dict[str, Any]] = {}
        for raw_line in payload.get("lines") or []:
            supplier_id = int(raw_line["supplier_id"])
            supplier = await SupplierProfileService._require_supplier(session, supplier_id)
            warehouse = await SupplyRequestService._resolve_warehouse(session, supplier_id, raw_line.get("warehouse_id"))
            payment_method = _payment_method(raw_line.get("payment_method"), supplier.default_payment_method)
            key = (supplier_id, warehouse.id if warehouse else None, payment_method, intent)
            request_meta[key] = {
                "supplier": supplier,
                "warehouse": warehouse,
                "payment_method": payment_method,
                "intent": intent,
                "comment": _clean_text(payload.get("comment")),
            }
            line_payload = {
                "source_type": "stock",
                "product_id": raw_line.get("product_id"),
                "supplier_offer_external_id": raw_line.get("supplier_offer_external_id"),
                "title": raw_line.get("title"),
                "qty": raw_line.get("qty"),
                "unit_cost": raw_line.get("unit_cost"),
                "comment": raw_line.get("comment"),
            }
            if line_payload["product_id"] and not line_payload["supplier_offer_external_id"]:
                offer = await SupplyRequestService._select_default_offer(
                    session,
                    int(line_payload["product_id"]),
                    supplier_id=supplier_id,
                )
                if offer:
                    line_payload["supplier_offer_external_id"] = offer.external_id
                    line_payload["unit_cost"] = await SupplyRequestService._offer_cost_decimal(session, offer)
                    line_payload["supplier_offer_title"] = offer.title_raw
            grouped[key].append(await SupplyRequestService._build_manual_line(session, line_payload, 0))

        requests = []
        for key, lines in grouped.items():
            meta = request_meta[key]
            supplier = meta["supplier"]
            warehouse = meta["warehouse"]
            supplier_contact = await SupplyRequestService._resolve_contact(
                session, supplier.id, None, default_flag="default_for_orders"
            )
            logistics_contact = await SupplyRequestService._resolve_contact(
                session, supplier.id, None, default_flag="default_for_logistics"
            )
            request = SupplyRequest(
                supplier_id=supplier.id,
                warehouse_id=warehouse.id if warehouse else None,
                supplier_contact_id=supplier_contact.id if supplier_contact else None,
                logistics_contact_id=logistics_contact.id if logistics_contact else None,
                intent=meta["intent"],
                payment_method=meta["payment_method"],
                comment=meta["comment"],
                created_by=created_by,
            )
            session.add(request)
            await session.flush()
            for line in lines:
                line.request_id = request.id
                session.add(line)
            requests.append(request)
        await session.commit()
        return {"items": [await SupplyRequestService.get_request(session, int(request.id)) for request in requests if request.id]}

    @staticmethod
    async def get_request(session: AsyncSession, request_id: int) -> dict:
        request = await SupplyRequestService._get_request_model(session, request_id)
        if not request:
            raise ValueError("Supply request not found")
        return SupplyRequestService._serialize_request(request)

    @staticmethod
    async def update_request(session: AsyncSession, request_id: int, payload: dict) -> dict:
        request = await session.get(SupplyRequest, request_id)
        if not request:
            raise ValueError("Supply request not found")
        data = dict(payload)
        if "status" in data and data["status"] is not None:
            request.status = _status(data["status"])
            await SupplyRequestService._set_active_lines_status(session, request.id, request.status)
        if "intent" in data and data["intent"] is not None:
            request.intent = _intent(data["intent"])
        if "payment_method" in data and data["payment_method"] is not None:
            request.payment_method = _payment_method(data["payment_method"])
        if "warehouse_id" in data:
            warehouse = await SupplyRequestService._resolve_warehouse(session, request.supplier_id, data.get("warehouse_id"))
            request.warehouse_id = warehouse.id if warehouse else None
        if "supplier_contact_id" in data:
            contact = await SupplyRequestService._resolve_contact(session, request.supplier_id, data.get("supplier_contact_id"))
            request.supplier_contact_id = contact.id if contact else None
        if "logistics_contact_id" in data:
            contact = await SupplyRequestService._resolve_contact(session, request.supplier_id, data.get("logistics_contact_id"))
            request.logistics_contact_id = contact.id if contact else None
        if "comment" in data:
            request.comment = _clean_text(data.get("comment"))
        request.updated_at = datetime.now()
        session.add(request)
        await session.commit()
        return await SupplyRequestService.get_request(session, request_id)

    @staticmethod
    async def update_line(session: AsyncSession, line_id: int, payload: dict) -> dict:
        line = await session.get(SupplyRequestLine, line_id)
        if not line:
            raise ValueError("Supply request line not found")
        data = dict(payload)
        if "status" in data and data["status"] is not None:
            line.status = _status(data["status"])
        if "reserved_until" in data:
            line.reserved_until = data.get("reserved_until")
        if "received_qty" in data and data["received_qty"] is not None:
            line.received_qty = max(0, int(data["received_qty"]))
            if line.received_qty >= line.qty:
                line.status = "received"
        if "comment" in data:
            line.comment = _clean_text(data.get("comment"))
        line.updated_at = datetime.now()
        session.add(line)
        await session.flush()
        await SupplyRequestService._sync_request_status_from_lines(session, line.request_id)
        await session.commit()
        return await SupplyRequestService.get_request(session, line.request_id)

    @staticmethod
    async def generate_supplier_message(session: AsyncSession, request_id: int, *, mark_sent: bool = False) -> dict:
        request = await SupplyRequestService._get_request_model(session, request_id)
        if not request:
            raise ValueError("Supply request not found")
        text = SupplyRequestService._supplier_message_text(request)
        if mark_sent:
            request.supplier_message_snapshot = text
            request.supplier_message_sent_at = datetime.now()
            request.status = "awaiting_reply" if request.intent == "reserve" else "ordered"
            await SupplyRequestService._set_active_lines_status(session, request.id, request.status)
            request.updated_at = datetime.now()
            session.add(request)
            await session.commit()
        return {"text": text, "request_ids": [request_id]}

    @staticmethod
    async def generate_logistics_message(
        session: AsyncSession,
        request_ids: list[int],
        *,
        mark_sent: bool = False,
    ) -> dict:
        if not request_ids:
            raise ValueError("Supply request IDs are required")
        result = await session.execute(
            select(SupplyRequest)
            .where(SupplyRequest.id.in_([int(x) for x in request_ids]))
            .options(
                selectinload(SupplyRequest.supplier),
                selectinload(SupplyRequest.warehouse),
                selectinload(SupplyRequest.supplier_contact),
                selectinload(SupplyRequest.logistics_contact),
                selectinload(SupplyRequest.lines).selectinload(SupplyRequestLine.product),
            )
            .order_by(SupplyRequest.supplier_id.asc(), SupplyRequest.warehouse_id.asc())
        )
        requests = list(result.scalars().all())
        if not requests:
            raise ValueError("Supply requests were not found")
        text = SupplyRequestService._logistics_message_text(requests)
        if mark_sent:
            now = datetime.now()
            for request in requests:
                request.logistics_message_snapshot = text
                request.logistics_message_sent_at = now
                if request.status in {"ordered", "awaiting_reply", "reserved"}:
                    request.status = "ready_for_pickup"
                    await SupplyRequestService._set_active_lines_status(session, request.id, "ready_for_pickup")
                request.updated_at = now
                session.add(request)
            await session.commit()
        return {"text": text, "request_ids": [int(r.id) for r in requests if r.id]}

    @staticmethod
    async def _get_request_model(session: AsyncSession, request_id: int) -> SupplyRequest | None:
        result = await session.execute(
            select(SupplyRequest)
            .where(SupplyRequest.id == request_id)
            .options(
                selectinload(SupplyRequest.supplier),
                selectinload(SupplyRequest.warehouse),
                selectinload(SupplyRequest.supplier_contact),
                selectinload(SupplyRequest.logistics_contact),
                selectinload(SupplyRequest.lines).selectinload(SupplyRequestLine.product),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _build_manual_line(session: AsyncSession, payload: dict, request_id: int) -> SupplyRequestLine:
        product_id = payload.get("product_id")
        product = await session.get(Product, int(product_id)) if product_id else None
        title = _clean_text(payload.get("title")) or (product.title if product else None)
        if not title:
            raise ValueError("Supply line title or product is required")
        qty = max(1, int(payload.get("qty") or 1))
        source_type = _source_type(payload.get("source_type"))
        supplier_offer_external_id = _clean_text(payload.get("supplier_offer_external_id"))
        supplier_offer_title = _clean_text(payload.get("supplier_offer_title"))
        return SupplyRequestLine(
            request_id=request_id,
            order_product_link_id=payload.get("order_product_link_id"),
            source_type=source_type,
            product_id=product.id if product else None,
            supplier_offer_external_id=supplier_offer_external_id,
            supplier_offer_title=supplier_offer_title,
            title_snapshot=title,
            qty=qty,
            unit_cost_snapshot=_decimal_or_none(payload.get("unit_cost")),
            status="draft",
            reserved_until=payload.get("reserved_until"),
            comment=_clean_text(payload.get("comment")),
        )

    @staticmethod
    async def _select_default_offer(
        session: AsyncSession,
        product_id: int,
        *,
        supplier_id: int | None = None,
    ) -> SupplierOffer | None:
        stmt = (
            select(SupplierOffer)
            .join(
                ProductSupplierMapping,
                and_(
                    ProductSupplierMapping.supplier_id == SupplierOffer.supplier_id,
                    ProductSupplierMapping.external_id == SupplierOffer.external_id,
                    ProductSupplierMapping.is_active.is_(True),
                ),
            )
            .where(
                ProductSupplierMapping.product_id == product_id,
                SupplierOffer.is_active.is_(True),
            )
        )
        if supplier_id:
            stmt = stmt.where(SupplierOffer.supplier_id == supplier_id)
        result = await session.execute(stmt)
        offers = list(result.scalars().all())
        if not offers:
            return None
        fx_rate = await FxRateService.get_supplier_usd_byn_rate(session)

        def sort_key(offer: SupplierOffer) -> tuple[int, float, int]:
            cost = ProductSupplyMetricsService._compute_cost_byn(
                offer.wholesale_value,
                offer.wholesale_currency,
                fx_rate,
            )
            return (0 if int(offer.qty or 0) > 0 else 1, cost if cost is not None else 999999999.0, offer.supplier_id)

        return sorted(offers, key=sort_key)[0]

    @staticmethod
    async def _offer_cost_decimal(session: AsyncSession, offer: SupplierOffer | None) -> Decimal | None:
        if not offer or offer.wholesale_value is None:
            return None
        fx_rate = await FxRateService.get_supplier_usd_byn_rate(session)
        cost_byn = ProductSupplyMetricsService._compute_cost_byn(
            offer.wholesale_value,
            offer.wholesale_currency,
            fx_rate,
        )
        if cost_byn is None:
            return Decimal(offer.wholesale_value).quantize(Decimal("0.01"))
        return Decimal(str(cost_byn)).quantize(Decimal("0.01"))

    @staticmethod
    async def _resolve_warehouse(
        session: AsyncSession,
        supplier_id: int,
        warehouse_id: int | None,
    ) -> SupplierWarehouse | None:
        if warehouse_id:
            warehouse = await session.get(SupplierWarehouse, int(warehouse_id))
            if not warehouse or warehouse.supplier_id != supplier_id:
                raise ValueError("Supplier warehouse not found")
            return warehouse
        result = await session.execute(
            select(SupplierWarehouse)
            .where(SupplierWarehouse.supplier_id == supplier_id)
            .order_by(SupplierWarehouse.is_default.desc(), SupplierWarehouse.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _resolve_contact(
        session: AsyncSession,
        supplier_id: int,
        contact_id: int | None,
        *,
        default_flag: str | None = None,
    ) -> SupplierContact | None:
        if contact_id:
            contact = await session.get(SupplierContact, int(contact_id))
            if not contact or contact.supplier_id != supplier_id:
                raise ValueError("Supplier contact not found")
            return contact
        if not default_flag:
            return None
        result = await session.execute(
            select(SupplierContact)
            .where(
                SupplierContact.supplier_id == supplier_id,
                getattr(SupplierContact, default_flag).is_(True),
            )
            .order_by(SupplierContact.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _set_active_lines_status(session: AsyncSession, request_id: int, status: str) -> None:
        result = await session.execute(select(SupplyRequestLine).where(SupplyRequestLine.request_id == request_id))
        for line in result.scalars().all():
            if line.status in {"received", "canceled"}:
                continue
            line.status = status
            line.updated_at = datetime.now()
            session.add(line)

    @staticmethod
    async def _sync_request_status_from_lines(session: AsyncSession, request_id: int) -> None:
        request = await session.get(SupplyRequest, request_id)
        if not request:
            return
        result = await session.execute(select(SupplyRequestLine).where(SupplyRequestLine.request_id == request_id))
        lines = list(result.scalars().all())
        if lines and all(line.status == "received" or line.received_qty >= line.qty for line in lines):
            request.status = "received"
        request.updated_at = datetime.now()
        session.add(request)

    @staticmethod
    def _serialize_request(request: SupplyRequest) -> dict:
        warehouse = request.warehouse
        supplier_contact = request.supplier_contact
        logistics_contact = request.logistics_contact
        return {
            "id": request.id,
            "supplier_id": request.supplier_id,
            "supplier_name": request.supplier.name if request.supplier else None,
            "warehouse_id": request.warehouse_id,
            "warehouse_name": warehouse.name if warehouse else None,
            "warehouse_address": warehouse.address if warehouse else None,
            "supplier_contact_id": request.supplier_contact_id,
            "supplier_contact_name": supplier_contact.name if supplier_contact else None,
            "logistics_contact_id": request.logistics_contact_id,
            "logistics_contact_name": logistics_contact.name if logistics_contact else None,
            "status": request.status,
            "intent": request.intent,
            "payment_method": request.payment_method,
            "comment": request.comment,
            "supplier_message_snapshot": request.supplier_message_snapshot,
            "logistics_message_snapshot": request.logistics_message_snapshot,
            "created_by": request.created_by,
            "supplier_message_sent_at": request.supplier_message_sent_at,
            "logistics_message_sent_at": request.logistics_message_sent_at,
            "created_at": request.created_at,
            "updated_at": request.updated_at,
            "lines": [SupplyRequestService._serialize_line(line) for line in request.lines],
        }

    @staticmethod
    def _serialize_line(line: SupplyRequestLine) -> dict:
        return {
            "id": line.id,
            "request_id": line.request_id,
            "order_product_link_id": line.order_product_link_id,
            "source_type": line.source_type,
            "product_id": line.product_id,
            "product_title": line.product.title if line.product else None,
            "supplier_offer_external_id": line.supplier_offer_external_id,
            "supplier_offer_title": line.supplier_offer_title,
            "title_snapshot": line.title_snapshot,
            "qty": line.qty,
            "unit_cost_snapshot": _line_cost_float(line),
            "status": line.status,
            "reserved_until": line.reserved_until,
            "received_qty": line.received_qty,
            "comment": line.comment,
            "created_at": line.created_at,
            "updated_at": line.updated_at,
        }

    @staticmethod
    def _contact_line(contact: SupplierContact | None, warehouse: SupplierWarehouse | None = None) -> str | None:
        if contact:
            parts = [contact.name]
            if contact.phone:
                parts.append(contact.phone)
            if contact.viber:
                parts.append(f"Viber: {contact.viber}")
            if contact.telegram_username:
                parts.append(f"Telegram: {contact.telegram_username}")
            return ", ".join(parts)
        if warehouse and (warehouse.contact_name or warehouse.contact_phone):
            return ", ".join([x for x in [warehouse.contact_name, warehouse.contact_phone] if x])
        return None

    @staticmethod
    def _payment_label(value: str) -> str:
        return {
            "cash": "наличные",
            "bank": "безнал",
            "mixed": "смешанная оплата",
            "unknown": "уточнить",
        }.get(value, "уточнить")

    @staticmethod
    def _supplier_message_text(request: SupplyRequest) -> str:
        action = "забронируйте" if request.intent == "reserve" else "подготовьте к отгрузке"
        lines = [
            "Здравствуйте.",
            f"Подтвердите наличие и {action}, пожалуйста:",
            "",
        ]
        for line in request.lines:
            cost = f", закупка {line.unit_cost_snapshot}" if line.unit_cost_snapshot is not None else ""
            offer = f" ({line.supplier_offer_external_id})" if line.supplier_offer_external_id else ""
            lines.append(f"- {line.title_snapshot}{offer} — {line.qty} шт.{cost}")
        lines.append("")
        lines.append(f"Оплата: {SupplyRequestService._payment_label(request.payment_method)}.")
        contact_line = SupplyRequestService._contact_line(request.supplier_contact)
        if contact_line:
            lines.append(f"Контакт: {contact_line}.")
        if request.warehouse:
            lines.append(f"Склад/отгрузка: {request.warehouse.name}, {request.warehouse.address}.")
        if request.comment:
            lines.append(f"Комментарий: {request.comment}.")
        return "\n".join(lines).strip()

    @staticmethod
    def _logistics_message_text(requests: list[SupplyRequest]) -> str:
        grouped: dict[tuple[int, int | None], list[SupplyRequest]] = defaultdict(list)
        for request in requests:
            grouped[(request.supplier_id, request.warehouse_id)].append(request)

        blocks: list[str] = []
        for (_supplier_id, _warehouse_id), rows in grouped.items():
            first = rows[0]
            warehouse = first.warehouse
            block = [f"Забрать у поставщика: {first.supplier.name if first.supplier else f'#{first.supplier_id}'}"]
            if warehouse:
                block.append(f"Склад: {warehouse.name}")
                block.append(f"Адрес: {warehouse.address}")
                contact_line = SupplyRequestService._contact_line(first.logistics_contact, warehouse)
                if contact_line:
                    block.append(f"Контакт склада: {contact_line}")
                if warehouse.work_hours:
                    block.append(f"Режим: {warehouse.work_hours}")
                if warehouse.pickup_notes:
                    block.append(f"Примечание склада: {warehouse.pickup_notes}")
            else:
                block.append("Склад: уточнить")
            block.append("Что забрать:")
            for request in rows:
                for line in request.lines:
                    block.append(f"- {line.title_snapshot} — {line.qty} шт.")
            payment_methods = sorted({SupplyRequestService._payment_label(r.payment_method) for r in rows})
            block.append(f"Оплата: {', '.join(payment_methods)}.")
            comments = [r.comment for r in rows if r.comment]
            if comments:
                block.append(f"Комментарий: {'; '.join(comments)}.")
            blocks.append("\n".join(block))
        return "\n\n".join(blocks).strip()
