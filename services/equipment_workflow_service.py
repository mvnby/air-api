from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import CustomerEquipment, EquipmentComponent, Order, OrderProductLink, Product
from services.equipment_service import EquipmentService
from services.tenant_scope_service import TenantScope


class EquipmentWorkflowService:
    @staticmethod
    async def create_equipment(
        session: AsyncSession,
        *,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        customer_id = int(payload["customer_id"])
        if not await EquipmentService._ensure_customer_exists(session, customer_id):
            return None
        customer_branch_id = payload.get("customer_branch_id")
        if customer_branch_id is not None:
            await EquipmentService._ensure_branch_for_customer(
                session,
                customer_id=customer_id,
                customer_branch_id=int(customer_branch_id),
            )
        catalog_product_id = payload.get("catalog_product_id")
        product = None
        if catalog_product_id is not None:
            product = await EquipmentService._ensure_product_exists(session, int(catalog_product_id))
        source_order_id = payload.get("source_order_id")
        source_order = None
        if source_order_id is not None:
            source_order = await EquipmentService._ensure_source_order_for_customer(
                session,
                customer_id=customer_id,
                source_order_id=int(source_order_id),
            )
            if customer_branch_id is None:
                customer_branch_id = source_order.customer_branch_id
            elif source_order.customer_branch_id is not None and int(customer_branch_id) != int(source_order.customer_branch_id):
                raise ValueError("Source order branch does not match equipment branch")

        data = {
            "equipment_type": EquipmentService._clean_optional_text(payload.get("equipment_type")) or "hvac",
            "equipment_source": EquipmentService._normalize_equipment_source(payload.get("equipment_source")),
            "display_name": EquipmentService._clean_optional_text(payload.get("display_name")),
            "brand": EquipmentService._clean_optional_text(payload.get("brand")),
            "model": EquipmentService._clean_optional_text(payload.get("model")),
            "serial": EquipmentService._clean_optional_text(payload.get("serial")),
            "inventory_number": EquipmentService._clean_optional_text(payload.get("inventory_number")),
            "location_hint": EquipmentService._clean_optional_text(payload.get("location_hint")),
            "refrigerant_type": EquipmentService._clean_optional_text(payload.get("refrigerant_type")),
            "installed_at": EquipmentService._normalize_naive_datetime(payload.get("installed_at")),
            "commissioned_at": EquipmentService._normalize_naive_datetime(payload.get("commissioned_at")),
            "warranty_started_at": EquipmentService._normalize_naive_datetime(payload.get("warranty_started_at")),
            "warranty_expires_at": EquipmentService._normalize_naive_datetime(payload.get("warranty_expires_at")),
            "warranty_terms": EquipmentService._clean_optional_text(payload.get("warranty_terms")),
            "notes": EquipmentService._clean_optional_text(payload.get("notes")),
        }
        data["display_name"] = EquipmentService._default_display_name(data)
        equipment = CustomerEquipment(
            customer_id=customer_id,
            customer_branch_id=int(customer_branch_id) if customer_branch_id is not None else None,
            catalog_product_id=int(catalog_product_id) if catalog_product_id is not None else None,
            source_order_id=int(source_order_id) if source_order_id is not None else None,
            **data,
            is_archived=bool(payload.get("is_archived", False)),
        )
        session.add(equipment)
        await session.flush()
        if source_order_id is not None:
            await EquipmentService._ensure_equipment_order_link(
                session,
                equipment_id=int(equipment.id or 0),
                order_id=int(source_order_id),
                role=payload.get("order_role") or "other",
            )
        from services.warranty_service import WarrantyService

        supplier_coverage = await WarrantyService.create_supplier_coverage(
            session,
            equipment=equipment,
            product=product,
            supplier_id=payload.get("supplier_id"),
            explicit_start=payload.get("warranty_started_at"),
            sale_at=getattr(source_order, "closed_at", None) or getattr(source_order, "created_at", None),
            manual_expires_at=payload.get("warranty_expires_at"),
            manual_terms=payload.get("warranty_terms"),
        )
        if supplier_coverage:
            equipment.warranty_started_at = supplier_coverage.starts_at
            equipment.warranty_expires_at = supplier_coverage.expires_at
            equipment.warranty_terms = supplier_coverage.terms_snapshot
            session.add(equipment)
        await WarrantyService.create_work_coverage(
            session,
            equipment=equipment,
            duration_months=payload.get("work_warranty_months"),
            starts_at=payload.get("installed_at") if payload.get("work_warranty_months") is not None else None,
            terms=payload.get("work_warranty_terms"),
            product=product,
            supplier_id=payload.get("supplier_id"),
            sale_at=getattr(source_order, "closed_at", None) or getattr(source_order, "created_at", None),
        )
        await session.commit()
        await session.refresh(equipment)
        return EquipmentService._to_equipment_item(equipment)

    @staticmethod
    async def update_equipment(
        session: AsyncSession,
        *,
        equipment_id: int,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        equipment = await EquipmentService._get_equipment(session, equipment_id)
        if not equipment:
            return None

        if "customer_branch_id" in payload:
            customer_branch_id = payload.get("customer_branch_id")
            if customer_branch_id is None:
                equipment.customer_branch_id = None
            else:
                await EquipmentService._ensure_branch_for_customer(
                    session,
                    customer_id=int(equipment.customer_id),
                    customer_branch_id=int(customer_branch_id),
                )
                equipment.customer_branch_id = int(customer_branch_id)

        if "catalog_product_id" in payload:
            catalog_product_id = payload.get("catalog_product_id")
            if catalog_product_id is None:
                equipment.catalog_product_id = None
            else:
                await EquipmentService._ensure_product_exists(session, int(catalog_product_id))
                equipment.catalog_product_id = int(catalog_product_id)

        if "source_order_id" in payload:
            source_order_id = payload.get("source_order_id")
            if source_order_id is None:
                equipment.source_order_id = None
            else:
                source_order = await EquipmentService._ensure_source_order_for_customer(
                    session,
                    customer_id=int(equipment.customer_id),
                    source_order_id=int(source_order_id),
                )
                if (
                    source_order.customer_branch_id is not None
                    and equipment.customer_branch_id is not None
                    and int(source_order.customer_branch_id) != int(equipment.customer_branch_id)
                ):
                    raise ValueError("Source order branch does not match equipment branch")
                equipment.source_order_id = int(source_order_id)

        text_fields = (
            "equipment_type",
            "equipment_source",
            "display_name",
            "brand",
            "model",
            "serial",
            "inventory_number",
            "location_hint",
            "refrigerant_type",
            "warranty_terms",
            "notes",
        )
        for field in text_fields:
            if field not in payload:
                continue
            value = EquipmentService._clean_optional_text(payload.get(field))
            if field == "equipment_type":
                equipment.equipment_type = value or "hvac"
            elif field == "equipment_source":
                equipment.equipment_source = EquipmentService._normalize_equipment_source(value)
            else:
                setattr(equipment, field, value)
        date_fields = (
            "installed_at",
            "commissioned_at",
            "warranty_started_at",
            "warranty_expires_at",
        )
        for field in date_fields:
            if field in payload:
                setattr(equipment, field, EquipmentService._normalize_naive_datetime(payload.get(field)))
        from services.equipment_warranty_bridge_service import EquipmentWarrantyBridgeService

        await EquipmentWarrantyBridgeService.sync_manual_fields(
            session,
            equipment=equipment,
            payload=payload,
        )
        if "is_archived" in payload and payload["is_archived"] is not None:
            equipment.is_archived = bool(payload["is_archived"])

        equipment.updated_at = datetime.now()
        session.add(equipment)
        await session.commit()
        await session.refresh(equipment)
        return EquipmentService._to_equipment_item(equipment)


    @staticmethod
    async def create_equipment_from_order(
        session: AsyncSession,
        *,
        order_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.customer_branch),
                selectinload(Order.proposals),
                selectinload(Order.product_links).selectinload(OrderProductLink.product).selectinload(Product.brand),
            )
        )
        order = result.scalars().first()
        if not order:
            raise ValueError("Order not found")
        if order.customer_id is None:
            raise ValueError("Order customer is required to create customer equipment")

        product_links = [link for link in EquipmentService._selected_order_product_links(order) if link.product_id is not None]
        if not product_links:
            raise ValueError("Selected order proposal has no catalog products")

        explicit_warranty_start = EquipmentService._order_warranty_start(order, payload)
        commissioned_at = explicit_warranty_start or order.installation_date or order.closed_at
        sale_at = order.closed_at or order.created_at
        supplier_id = int(payload["supplier_id"]) if payload.get("supplier_id") is not None else None
        work_warranty_months = payload.get("work_warranty_months")
        order_role = EquipmentService._normalize_order_link_role(payload.get("order_role") or "sale")
        include_placeholders = bool(payload.get("include_component_placeholders", True))
        created_ids: list[int] = []
        skipped_count = 0
        product_quantities: dict[int, int] = {}
        first_link_by_product: dict[int, OrderProductLink] = {}
        for link in product_links:
            product_id = int(link.product_id)
            product_quantities[product_id] = product_quantities.get(product_id, 0) + max(1, int(link.quantity or 1))
            first_link_by_product.setdefault(product_id, link)

        for product_id, quantity in product_quantities.items():
            link = first_link_by_product[product_id]
            existing_equipment_result = await session.execute(
                select(CustomerEquipment).where(
                    CustomerEquipment.source_order_id == order_id,
                    CustomerEquipment.catalog_product_id == product_id,
                    CustomerEquipment.is_archived == False,
                )
            )
            existing_equipment = list(existing_equipment_result.scalars().all())
            existing_count = len(existing_equipment)
            for current_equipment in existing_equipment:
                await EquipmentService._ensure_equipment_order_link(
                    session,
                    equipment_id=int(current_equipment.id or 0),
                    order_id=order_id,
                    role=order_role,
                )
            missing_count = max(0, quantity - existing_count)
            skipped_count += quantity - missing_count
            if missing_count <= 0:
                continue

            product = link.product
            product_title = EquipmentService._clean_optional_text(getattr(product, "title", None)) or f"Товар #{product_id}"
            brand = EquipmentService._product_brand_title(product)
            location_hint = EquipmentService._clean_optional_text(
                order.delivery_address or (order.customer_branch.delivery_address if order.customer_branch else None)
            )
            refrigerant_type = EquipmentService._product_spec_text(product, "refrigerant", "refrigerant_type", "хладагент")
            indoor_model = EquipmentService._product_spec_text(
                product,
                "indoor_model",
                "indoor_unit_model",
                "модель внутреннего блока",
                "внутренний блок",
            )
            outdoor_model = EquipmentService._product_spec_text(
                product,
                "outdoor_model",
                "outdoor_unit_model",
                "модель наружного блока",
                "наружный блок",
            )

            for index in range(missing_count):
                suffix = f" #{existing_count + index + 1}" if quantity > 1 else ""
                equipment = CustomerEquipment(
                    customer_id=int(order.customer_id),
                    customer_branch_id=order.customer_branch_id,
                    catalog_product_id=product_id,
                    source_order_id=order_id,
                    equipment_type="hvac",
                    equipment_source="sold_by_us",
                    display_name=f"{product_title}{suffix}",
                    brand=brand,
                    model=product_title,
                    location_hint=location_hint,
                    refrigerant_type=refrigerant_type,
                    installed_at=EquipmentService._normalize_naive_datetime(order.installation_date),
                    commissioned_at=commissioned_at,
                    notes=f"Создано из заказа #{order_id}, строка товара #{link.id or product_id}.",
                )
                session.add(equipment)
                await session.flush()
                created_ids.append(int(equipment.id or 0))
                await EquipmentService._ensure_equipment_order_link(
                    session,
                    equipment_id=int(equipment.id or 0),
                    order_id=order_id,
                    role=order_role,
                )

                if include_placeholders:
                    session.add(
                        EquipmentComponent(
                            equipment_id=int(equipment.id or 0),
                            catalog_product_id=product_id,
                            component_type="indoor_unit",
                            title="Внутренний блок",
                            brand=brand,
                            model=indoor_model,
                        )
                    )
                    session.add(
                        EquipmentComponent(
                            equipment_id=int(equipment.id or 0),
                            catalog_product_id=product_id,
                            component_type="outdoor_unit",
                            title="Наружный блок",
                            brand=brand,
                            model=outdoor_model,
                        )
                    )
                else:
                    session.add(
                        EquipmentComponent(
                            equipment_id=int(equipment.id or 0),
                            catalog_product_id=product_id,
                            component_type="system",
                            title=product_title,
                            brand=brand,
                            model=product_title,
                        )
                    )

                from services.warranty_service import WarrantyService

                supplier_coverage = await WarrantyService.create_supplier_coverage(
                    session,
                    equipment=equipment,
                    product=product,
                    supplier_id=supplier_id,
                    explicit_start=explicit_warranty_start,
                    sale_at=sale_at,
                )
                if supplier_coverage:
                    equipment.warranty_started_at = supplier_coverage.starts_at
                    equipment.warranty_expires_at = supplier_coverage.expires_at
                    equipment.warranty_terms = supplier_coverage.terms_snapshot
                    session.add(equipment)
                await WarrantyService.create_work_coverage(
                    session,
                    equipment=equipment,
                    duration_months=work_warranty_months,
                    starts_at=order.installation_date if work_warranty_months is not None else None,
                    terms=payload.get("work_warranty_terms"),
                    product=product,
                    supplier_id=supplier_id,
                    sale_at=sale_at,
                )

        await session.commit()

        items = []
        for equipment_id in created_ids:
            detail = await EquipmentService.get_equipment_detail(
                session,
                equipment_id=equipment_id,
                history_limit=0,
            )
            if detail:
                items.append(detail)
        return {
            "items": items,
            "created_count": len(items),
            "skipped_count": skipped_count,
        }

    @staticmethod
    async def create_maintenance_order(
        session: AsyncSession,
        *,
        equipment_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        result = await session.execute(
            select(CustomerEquipment)
            .where(CustomerEquipment.id == equipment_id)
            .options(
                selectinload(CustomerEquipment.customer),
                selectinload(CustomerEquipment.customer_branch),
            )
        )
        equipment = result.scalars().first()
        if not equipment or equipment.is_archived or not equipment.customer:
            return None

        from schemas import ManagerOrderCreatePayload
        from services.order_service import OrderService

        branch = equipment.customer_branch
        address = (
            branch.delivery_address
            if branch
            else equipment.location_hint or equipment.customer.actual_address or equipment.customer.legal_address
        )
        equipment_title = equipment.display_name or equipment.model or f"Оборудование #{equipment_id}"
        payload = ManagerOrderCreatePayload(
            customer_id=int(equipment.customer_id),
            name=equipment.customer.name,
            phone=equipment.customer.phone,
            source="manager",
            request_text=f"Плановое техническое обслуживание: {equipment_title}",
            service_type="maintenance",
            customer_type=(
                equipment.customer.type.value
                if hasattr(equipment.customer.type, "value")
                else str(equipment.customer.type)
            ),
            address=address,
        )
        created = await OrderService.create_manager_order(
            session=session,
            payload=payload,
            tenant_scope=tenant_scope,
        )
        if not created:
            raise ValueError("Maintenance order could not be created")
        order_id = int(created["id"])
        order = await session.get(Order, order_id)
        if not order:
            raise ValueError("Created maintenance order not found")
        order.customer_branch_id = equipment.customer_branch_id
        order.technical_meta = {
            **(order.technical_meta or {}),
            "equipment_id": equipment_id,
            "equipment_display_name": equipment_title,
        }
        session.add(order)
        await EquipmentService._ensure_equipment_order_link(
            session,
            equipment_id=equipment_id,
            order_id=order_id,
            role="maintenance",
        )
        await session.commit()
        return await OrderService.get_order_detail_for_manager(session, order_id)
