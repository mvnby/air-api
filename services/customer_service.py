from typing import Any, Dict, Optional

from sqlalchemy import exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerType, Order


class CustomerService:
    @staticmethod
    def _to_manager_item(
        customer: Customer,
        *,
        order_count: int,
        last_delivery_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "id": int(customer.id or 0),
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "type": customer.type.value if hasattr(customer.type, "value") else str(customer.type),
            "inn": customer.inn,
            "kpp": customer.kpp,
            "full_legal_name": customer.full_legal_name,
            "legal_address": customer.legal_address,
            "actual_address": customer.actual_address,
            "iban": customer.iban,
            "bic": customer.bic,
            "bank_name": customer.bank_name,
            "signer_position": customer.signer_position,
            "signer_name": customer.signer_name,
            "acting_basis": customer.acting_basis,
            "last_delivery_address": last_delivery_address,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
            "order_count": order_count,
            "is_archived": customer.is_archived,
        }

    @staticmethod
    async def _get_last_delivery_address(session: AsyncSession, customer_id: int) -> Optional[str]:
        last_delivery_result = await session.execute(
            select(Order.delivery_address)
            .where(Order.customer_id == customer_id, Order.delivery_address.is_not(None))
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        return last_delivery_result.scalar_one_or_none()

    @staticmethod
    async def get_for_manager(session: AsyncSession, customer_id: int) -> Optional[Dict[str, Any]]:
        customer = await session.get(Customer, customer_id)
        if not customer:
            return None

        order_count_result = await session.execute(
            select(func.count(Order.id)).where(Order.customer_id == customer_id)
        )
        order_count = int(order_count_result.scalar() or 0)
        last_delivery_address = await CustomerService._get_last_delivery_address(session=session, customer_id=customer_id)

        return CustomerService._to_manager_item(
            customer,
            order_count=order_count,
            last_delivery_address=last_delivery_address,
        )

    @staticmethod
    async def update_for_manager(
        session: AsyncSession,
        *,
        customer_id: int,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        customer = await session.get(Customer, customer_id)
        if not customer:
            return None

        optional_text_fields = (
            "email",
            "inn",
            "kpp",
            "full_legal_name",
            "legal_address",
            "actual_address",
            "bank_name",
            "bic",
            "iban",
            "signer_position",
            "signer_name",
            "acting_basis",
        )

        if "name" in payload and payload["name"] is not None:
            customer.name = str(payload["name"]).strip()

        if "phone" in payload and payload["phone"] is not None:
            customer.phone = str(payload["phone"]).strip()

        if "type" in payload and payload["type"]:
            customer.type = CustomerType(str(payload["type"]).strip().lower())

        for field in optional_text_fields:
            if field not in payload:
                continue
            value = payload[field]
            if value is None:
                setattr(customer, field, None)
                continue
            trimmed = str(value).strip()
            setattr(customer, field, trimmed or None)

        session.add(customer)
        await session.commit()

        return await CustomerService.get_for_manager(session=session, customer_id=customer_id)

    @staticmethod
    async def list_for_manager(
        session: AsyncSession,
        page: int,
        limit: int,
        search: Optional[str] = None,
        customer_type: Optional[str] = None,
        only_with_orders: bool = True,
        include_archived: bool = False,
    ) -> Dict[str, Any]:
        stmt = select(Customer)
        count_stmt = select(func.count(Customer.id))

        # Hide archived customers unless explicitly requested
        if not include_archived:
            stmt = stmt.where(Customer.is_archived == False)
            count_stmt = count_stmt.where(Customer.is_archived == False)

        if only_with_orders:
            has_orders_clause = exists(select(Order.id).where(Order.customer_id == Customer.id))
            stmt = stmt.where(has_orders_clause)
            count_stmt = count_stmt.where(has_orders_clause)

        if search:
            search_clause = or_(
                Customer.name.ilike(f"%{search}%"),
                Customer.phone.ilike(f"%{search}%"),
                Customer.inn.ilike(f"%{search}%"),
                Customer.email.ilike(f"%{search}%"),
            )
            stmt = stmt.where(search_clause)
            count_stmt = count_stmt.where(search_clause)

        if customer_type:
            stmt = stmt.where(Customer.type == customer_type)
            count_stmt = count_stmt.where(Customer.type == customer_type)

        stmt = stmt.order_by(Customer.created_at.desc())
        stmt = stmt.offset((page - 1) * limit).limit(limit)

        result = await session.execute(stmt)
        customers = result.scalars().all()

        total_result = await session.execute(count_stmt)
        total = int(total_result.scalar() or 0)

        customer_ids = [c.id for c in customers if c.id is not None]
        order_counts: Dict[int, int] = {}
        if customer_ids:
            oc_stmt = (
                select(Order.customer_id, func.count(Order.id))
                .where(Order.customer_id.in_(customer_ids))
                .group_by(Order.customer_id)
            )
            oc_result = await session.execute(oc_stmt)
            order_counts = {int(k): int(v) for k, v in oc_result.all() if k is not None}

        items = []
        for customer in customers:
            cid = int(customer.id or 0)
            items.append(CustomerService._to_manager_item(customer, order_count=order_counts.get(cid, 0)))

        return {
            "items": items,
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit if limit else 1,
            },
        }

    @staticmethod
    async def delete_for_manager(session: AsyncSession, customer_id: int) -> bool:
        customer = await session.get(Customer, customer_id)
        if not customer:
            return False
            
        # Check if customer has any orders
        order_check = await session.execute(
            select(Order.id).where(Order.customer_id == customer_id).limit(1)
        )
        has_orders = order_check.scalar_one_or_none() is not None
        
        if has_orders:
            raise ValueError("Невозможно удалить клиента, так как у него есть связанные заказы.")
            
        await session.delete(customer)
        await session.commit()
        return True
