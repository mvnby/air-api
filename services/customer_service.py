from typing import Any, Dict, Optional

from sqlalchemy import exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerBranch, CustomerType, Order
from models.tenancy import TenantScope
from services.tenant_scope_service import (
    tenant_scope_clause,
)


class CustomerService:
    @staticmethod
    def _clean_optional(value: Any) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _to_branch_item(branch: CustomerBranch) -> Dict[str, Any]:
        return {
            "id": int(branch.id or 0),
            "customer_id": int(branch.customer_id),
            "name": branch.name,
            "delivery_address": branch.delivery_address,
            "contact_name": branch.contact_name,
            "contact_phone": branch.contact_phone,
            "is_default": bool(branch.is_default),
            "created_at": branch.created_at.isoformat() if branch.created_at else None,
            "updated_at": branch.updated_at.isoformat() if branch.updated_at else None,
        }

    @staticmethod
    def _to_manager_item(
        customer: Customer,
        *,
        order_count: int,
        last_delivery_address: Optional[str] = None,
        branches: Optional[list[dict[str, Any]]] = None,
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
            "is_favorite": customer.is_favorite,
            "branches": branches or [],
        }

    @staticmethod
    async def _get_customer_entity(
        session: AsyncSession,
        *,
        customer_id: int,
        tenant_scope: TenantScope,
        lock: bool = False,
    ) -> Optional[Customer]:
        statement = select(Customer).where(
            Customer.id == customer_id,
            tenant_scope_clause(Customer, tenant_scope),
        )
        if lock:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    @staticmethod
    async def _get_last_delivery_address(
        session: AsyncSession,
        customer_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[str]:
        last_delivery_result = await session.execute(
            select(Order.delivery_address)
            .where(
                Order.customer_id == customer_id,
                Order.delivery_address.is_not(None),
                tenant_scope_clause(Order, tenant_scope),
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        return last_delivery_result.scalar_one_or_none()

    @staticmethod
    async def get_for_manager(
        session: AsyncSession,
        customer_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = await CustomerService._get_customer_entity(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if not customer:
            return None

        order_count_result = await session.execute(
            select(func.count(Order.id)).where(
                Order.customer_id == customer_id,
                tenant_scope_clause(Order, tenant_scope),
            )
        )
        order_count = int(order_count_result.scalar() or 0)
        last_delivery_address = await CustomerService._get_last_delivery_address(
            session=session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        branches = await CustomerService.list_branches_for_manager(
            session=session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )

        return CustomerService._to_manager_item(
            customer,
            order_count=order_count,
            last_delivery_address=last_delivery_address,
            branches=branches["items"] if branches else [],
        )

    @staticmethod
    async def list_branches_for_manager(
        session: AsyncSession,
        customer_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = await CustomerService._get_customer_entity(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if not customer:
            return None

        result = await session.execute(
            select(CustomerBranch)
            .where(CustomerBranch.customer_id == customer_id)
            .order_by(CustomerBranch.is_default.desc(), CustomerBranch.created_at.asc(), CustomerBranch.id.asc())
        )
        branches = list(result.scalars().all())
        return {"items": [CustomerService._to_branch_item(branch) for branch in branches]}

    @staticmethod
    async def create_branch_for_manager(
        session: AsyncSession,
        *,
        customer_id: int,
        payload: Dict[str, Any],
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = await CustomerService._get_customer_entity(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if not customer:
            return None

        delivery_address = CustomerService._clean_optional(payload.get("delivery_address"))
        if not delivery_address:
            raise ValueError("Адрес филиала обязателен")

        requested_default = bool(payload.get("is_default"))
        first_branch_result = await session.execute(
            select(func.count(CustomerBranch.id)).where(CustomerBranch.customer_id == customer_id)
        )
        has_existing_branches = int(first_branch_result.scalar() or 0) > 0
        effective_default = requested_default or (not has_existing_branches)

        if effective_default:
            await session.execute(
                CustomerBranch.__table__.update()
                .where(CustomerBranch.customer_id == customer_id)
                .values(is_default=False)
            )

        branch = CustomerBranch(
            customer_id=customer_id,
            name=CustomerService._clean_optional(payload.get("name")),
            delivery_address=delivery_address,
            contact_name=CustomerService._clean_optional(payload.get("contact_name")),
            contact_phone=CustomerService._clean_optional(payload.get("contact_phone")),
            is_default=effective_default,
        )
        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return CustomerService._to_branch_item(branch)

    @staticmethod
    async def update_branch_for_manager(
        session: AsyncSession,
        *,
        customer_id: int,
        branch_id: int,
        payload: Dict[str, Any],
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = await CustomerService._get_customer_entity(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if not customer:
            return None

        branch = await session.get(CustomerBranch, branch_id)
        if not branch or int(branch.customer_id) != int(customer_id):
            return None

        if "name" in payload:
            branch.name = CustomerService._clean_optional(payload.get("name"))
        if "delivery_address" in payload:
            delivery_address = CustomerService._clean_optional(payload.get("delivery_address"))
            if not delivery_address:
                raise ValueError("Адрес филиала обязателен")
            branch.delivery_address = delivery_address
        if "contact_name" in payload:
            branch.contact_name = CustomerService._clean_optional(payload.get("contact_name"))
        if "contact_phone" in payload:
            branch.contact_phone = CustomerService._clean_optional(payload.get("contact_phone"))

        if payload.get("is_default") is True:
            await session.execute(
                CustomerBranch.__table__.update()
                .where(CustomerBranch.customer_id == customer_id)
                .values(is_default=False)
            )
            branch.is_default = True
        elif payload.get("is_default") is False:
            branch.is_default = False

        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return CustomerService._to_branch_item(branch)

    @staticmethod
    async def delete_branch_for_manager(
        session: AsyncSession,
        *,
        customer_id: int,
        branch_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[bool]:
        customer = await CustomerService._get_customer_entity(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if not customer:
            return None

        branch = await session.get(CustomerBranch, branch_id)
        if not branch or int(branch.customer_id) != int(customer_id):
            return None

        was_default = bool(branch.is_default)
        await session.delete(branch)
        await session.flush()

        if was_default:
            next_branch_result = await session.execute(
                select(CustomerBranch)
                .where(CustomerBranch.customer_id == customer_id)
                .order_by(CustomerBranch.created_at.asc(), CustomerBranch.id.asc())
                .limit(1)
            )
            next_branch = next_branch_result.scalars().first()
            if next_branch:
                next_branch.is_default = True
                session.add(next_branch)

        await session.commit()
        return True

    @staticmethod
    async def update_for_manager(
        session: AsyncSession,
        *,
        customer_id: int,
        payload: Dict[str, Any],
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = await CustomerService._get_customer_entity(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
            lock=True,
        )
        if not customer:
            return None
        if customer.tenant_id is None:
            customer.tenant_id = tenant_scope.tenant_id

        defaulted_text_fields = {
            "signer_position": "директора",
            "acting_basis": "Устава",
        }
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
            "signer_name",
        )

        if "name" in payload and payload["name"] is not None:
            customer.name = str(payload["name"]).strip()

        if "phone" in payload and payload["phone"] is not None:
            customer.phone = str(payload["phone"]).strip()

        if "type" in payload and payload["type"]:
            customer.type = CustomerType(str(payload["type"]).strip().lower())

        if "is_favorite" in payload and payload["is_favorite"] is not None:
            customer.is_favorite = bool(payload["is_favorite"])

        for field, default_value in defaulted_text_fields.items():
            if field not in payload:
                continue
            value = payload[field]
            trimmed = str(value).strip() if value is not None else ""
            setattr(customer, field, trimmed or default_value)

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

        return await CustomerService.get_for_manager(
            session=session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def list_for_manager(
        session: AsyncSession,
        *,
        page: int,
        limit: int,
        search: Optional[str] = None,
        customer_type: Optional[str] = None,
        only_with_orders: bool = True,
        include_archived: bool = False,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        customer_scope_clause = tenant_scope_clause(
            Customer,
            tenant_scope,
        )
        stmt = select(Customer).where(customer_scope_clause)
        count_stmt = select(func.count(Customer.id)).where(customer_scope_clause)

        # Hide archived customers unless explicitly requested
        if not include_archived:
            stmt = stmt.where(Customer.is_archived == False)
            count_stmt = count_stmt.where(Customer.is_archived == False)

        if only_with_orders:
            has_orders_clause = exists(
                select(Order.id).where(
                    Order.customer_id == Customer.id,
                    tenant_scope_clause(Order, tenant_scope),
                )
            )
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

        stmt = stmt.order_by(Customer.is_favorite.desc(), Customer.created_at.desc())
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
                .where(
                    Order.customer_id.in_(customer_ids),
                    tenant_scope_clause(Order, tenant_scope),
                )
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
    async def delete_for_manager(
        session: AsyncSession,
        customer_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> bool:
        customer = await CustomerService._get_customer_entity(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
            lock=True,
        )
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
