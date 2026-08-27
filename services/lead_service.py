from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import re

from sqlalchemy import String, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Customer,
    CustomerBranch,
    CustomerType,
    Lead,
    LeadIntakeSource,
    LeadSegmentHint,
    LeadSource as OrderLeadSource,
    LeadStatus,
    Order,
    OrderStatus,
)
from schemas import Meta
from services.tenant_scope_service import (
    TenantScope,
    storefront_scope_clause,
    tenant_scope_clause,
)
from services.customer_party import (
    is_business_customer_type,
    signing_mode_for_customer_type,
)
from services.tenant_entity_access_service import TenantEntityAccessService


class LeadService:
    @staticmethod
    def _normalize_phone_digits(value: Optional[str]) -> str:
        if not value:
            return ""
        return re.sub(r"\D", "", value)

    @staticmethod
    def _customer_data_completeness_score(customer: Customer) -> int:
        score = 0
        if customer.full_legal_name:
            score += 3
        if customer.legal_address:
            score += 3
        if customer.bank_name:
            score += 2
        if customer.bic:
            score += 2
        if customer.iban:
            score += 3
        if customer.email:
            score += 1
        if customer.phone:
            score += 1
        if customer.actual_address:
            score += 1
        return score

    @staticmethod
    def _customer_match_priority_score(
        customer: Customer,
        phone: Optional[str],
        email: Optional[str],
        inn: Optional[str],
    ) -> int:
        score = 0
        normalized_email = (email or "").strip().lower()
        normalized_phone = LeadService._normalize_phone_digits(phone)
        customer_email = (customer.email or "").strip().lower()
        customer_phone = LeadService._normalize_phone_digits(customer.phone)

        if inn and customer.inn and customer.inn == inn:
            score += 300
        if normalized_phone and customer_phone and customer_phone == normalized_phone:
            score += 200
        if normalized_email and customer_email and customer_email == normalized_email:
            score += 100
        score += LeadService._customer_data_completeness_score(customer)
        return score

    @staticmethod
    def _clean_optional(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _normalize_segment_hint(inn: Optional[str], explicit_hint: Optional[str] = None) -> LeadSegmentHint:
        if inn and inn.strip():
            return LeadSegmentHint.b2b

        if explicit_hint:
            try:
                return LeadSegmentHint(explicit_hint)
            except ValueError as exc:
                raise ValueError(f"Invalid segment_hint: {explicit_hint}") from exc

        return LeadSegmentHint.unknown

    @staticmethod
    def _normalize_naive_datetime(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _order_source_for_lead(lead: Lead) -> OrderLeadSource:
        source_value = lead.source.value if hasattr(lead.source, "value") else str(lead.source or "")
        mapping = {
            LeadIntakeSource.phone.value: OrderLeadSource.PHONE,
            LeadIntakeSource.site.value: OrderLeadSource.SITE,
            LeadIntakeSource.bot.value: OrderLeadSource.BOT,
            LeadIntakeSource.email.value: OrderLeadSource.EMAIL,
            LeadIntakeSource.manager.value: OrderLeadSource.MANAGER,
            LeadIntakeSource.other.value: OrderLeadSource.OTHER,
        }
        return mapping.get(source_value, OrderLeadSource.MANAGER)

    @staticmethod
    def _map_lead(lead: Lead) -> Dict[str, Any]:
        return {
            "id": int(lead.id or 0),
            "status": lead.status.value if hasattr(lead.status, "value") else str(lead.status),
            "source": lead.source.value if hasattr(lead.source, "value") else str(lead.source),
            "segment_hint": lead.segment_hint.value if hasattr(lead.segment_hint, "value") else str(lead.segment_hint),
            "name": lead.name,
            "phone": lead.phone,
            "email": lead.email,
            "inn": lead.inn,
            "company_name": lead.company_name,
            "request_text": lead.request_text,
            "source_message_id": lead.source_message_id,
            "source_fingerprint": lead.source_fingerprint,
            "loss_reason": lead.loss_reason.value if hasattr(lead.loss_reason, "value") else lead.loss_reason,
            "next_followup_date": lead.next_followup_date,
            "archived_at": lead.archived_at,
            "converted_order_id": lead.converted_order_id,
            "created_at": lead.created_at,
            "updated_at": lead.updated_at,
        }

    @staticmethod
    async def create_lead(
        session: AsyncSession,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        """Compatibility delegate to the transactional Lead command."""
        from services.lead_command_service import LeadCommandService

        return await LeadCommandService.create_lead(
            session,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def list_leads(
        session: AsyncSession,
        page: int,
        limit: int,
        *,
        tenant_scope: TenantScope,
        status: Optional[str] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
        overdue_only: bool = False,
        include_archived: bool = False,
        sort: str = "created_at_desc",
    ) -> Dict[str, Any]:
        ownership_clause = TenantEntityAccessService.lead_clause(tenant_scope)
        stmt = select(Lead).where(ownership_clause)
        count_stmt = select(func.count(Lead.id)).where(ownership_clause)

        if not include_archived:
            stmt = stmt.where(Lead.archived_at.is_(None))
            count_stmt = count_stmt.where(Lead.archived_at.is_(None))

        if status:
            try:
                status_enum = LeadStatus(status)
            except ValueError as exc:
                raise ValueError(f"Invalid status: {status}") from exc

            stmt = stmt.where(Lead.status == status_enum)
            count_stmt = count_stmt.where(Lead.status == status_enum)
        else:
            active_statuses = [LeadStatus.new, LeadStatus.contacted]
            stmt = stmt.where(Lead.status.in_(active_statuses))
            count_stmt = count_stmt.where(Lead.status.in_(active_statuses))

        if source:
            try:
                source_enum = LeadIntakeSource(source)
            except ValueError as exc:
                raise ValueError(f"Invalid source: {source}") from exc

            stmt = stmt.where(Lead.source == source_enum)
            count_stmt = count_stmt.where(Lead.source == source_enum)

        if search and search.strip():
            like = f"%{search.strip()}%"
            search_clause = or_(
                Lead.name.ilike(like),
                Lead.phone.ilike(like),
                Lead.email.ilike(like),
                Lead.inn.ilike(like),
                Lead.company_name.ilike(like),
                Lead.request_text.ilike(like),
                cast(Lead.id, String).ilike(like),
            )
            stmt = stmt.where(search_clause)
            count_stmt = count_stmt.where(search_clause)

        if overdue_only:
            now = datetime.now()
            stmt = stmt.where(Lead.next_followup_date.is_not(None), Lead.next_followup_date < now)
            count_stmt = count_stmt.where(Lead.next_followup_date.is_not(None), Lead.next_followup_date < now)

        sort_map = {
            "created_at_desc": Lead.created_at.desc(),
            "created_at_asc": Lead.created_at.asc(),
            "updated_at_desc": Lead.updated_at.desc().nullslast(),
            "updated_at_asc": Lead.updated_at.asc().nullslast(),
            "followup_asc": Lead.next_followup_date.asc().nullslast(),
            "followup_desc": Lead.next_followup_date.desc().nullslast(),
        }
        stmt = stmt.order_by(sort_map.get(sort, Lead.created_at.desc())).offset((page - 1) * limit).limit(limit)

        total_result = await session.execute(count_stmt)
        total = int(total_result.scalar() or 0)

        result = await session.execute(stmt)
        leads = list(result.scalars().all())

        pages = (total + limit - 1) // limit if limit > 0 else 0
        return {
            "items": [LeadService._map_lead(item) for item in leads],
            "meta": Meta(total=total, page=page, limit=limit, pages=pages),
        }

    @staticmethod
    async def update_lead(
        session: AsyncSession,
        lead_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility delegate to the transactional Lead command."""
        from services.lead_command_service import LeadCommandService

        return await LeadCommandService.update_lead(
            session,
            lead_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def mark_lead_lost(
        session: AsyncSession,
        lead_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility delegate to the transactional Lead command."""
        from services.lead_command_service import LeadCommandService

        return await LeadCommandService.mark_lead_lost(
            session,
            lead_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def _find_existing_customer(
        session: AsyncSession,
        phone: Optional[str],
        email: Optional[str],
        inn: Optional[str],
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Customer]:
        normalized_email = (email or "").strip().lower()
        normalized_phone = LeadService._normalize_phone_digits(phone)

        predicates = []
        if normalized_phone:
            phone_digits_expr = func.regexp_replace(func.coalesce(Customer.phone, ""), r"\D", "", "g")
            predicates.append(phone_digits_expr == normalized_phone)
        if normalized_email:
            predicates.append(func.lower(Customer.email) == normalized_email)
        if inn:
            predicates.append(Customer.inn == inn)
        if not predicates:
            return None

        result = await session.execute(
            select(Customer).where(
                or_(*predicates),
                tenant_scope_clause(Customer, tenant_scope),
            )
        )
        customers = result.scalars().all()
        if not customers:
            return None

        customers.sort(
            key=lambda item: (
                LeadService._customer_match_priority_score(item, phone=phone, email=email, inn=inn),
                item.created_at.timestamp() if item.created_at else 0,
                int(item.id or 0),
            ),
            reverse=True,
        )
        return customers[0]

    @staticmethod
    async def qualify_lead(
        session: AsyncSession,
        lead_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility delegate to the transactional Lead command."""
        from services.lead_command_service import LeadCommandService

        return await LeadCommandService.qualify_lead(
            session,
            lead_id,
            payload,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def _qualify_lead_mutation(
        session: AsyncSession,
        lead_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        lead = await TenantEntityAccessService.get_lead(
            session,
            lead_id,
            tenant_scope=tenant_scope,
            for_update=True,
        )
        if not lead:
            return None
        if lead.tenant_id is None:
            lead.tenant_id = tenant_scope.tenant_id
        if lead.storefront_id is None:
            lead.storefront_id = tenant_scope.storefront_id
        if lead.status in {LeadStatus.spam, LeadStatus.lost}:
            raise ValueError("Cannot qualify a lost/spam lead")
        if lead.status == LeadStatus.qualified:
            if not lead.converted_order_id:
                raise ValueError("Lead is already qualified")
            converted_order = (
                await session.execute(
                    select(Order).where(
                        Order.id == int(lead.converted_order_id),
                        storefront_scope_clause(
                            Order,
                            tenant_scope,
                        ),
                    )
                )
            ).scalars().first()
            if not converted_order:
                raise ValueError("Converted order not found")
            return {
                "lead": LeadService._map_lead(lead),
                "customer_id": int(converted_order.customer_id or 0),
                "order_id": int(converted_order.id),
                "order_created": False,
            }

        name = LeadService._clean_optional(payload.name) or LeadService._clean_optional(lead.name)
        phone = LeadService._clean_optional(payload.phone) or LeadService._clean_optional(lead.phone)
        email = LeadService._clean_optional(payload.email) or LeadService._clean_optional(lead.email)
        inn = LeadService._clean_optional(payload.inn) or LeadService._clean_optional(lead.inn)
        full_legal_name = LeadService._clean_optional(payload.full_legal_name) or LeadService._clean_optional(lead.company_name)
        legal_address = LeadService._clean_optional(payload.legal_address)
        iban = LeadService._clean_optional(payload.iban)
        bic = LeadService._clean_optional(payload.bic)
        bank_name = LeadService._clean_optional(payload.bank_name)

        customer = None
        selected_customer_id = getattr(payload, "customer_id", None)
        selected_customer_branch_id = getattr(payload, "customer_branch_id", None)
        if selected_customer_id:
            customer = (
                await session.execute(
                    select(Customer).where(
                        Customer.id == int(selected_customer_id),
                        tenant_scope_clause(
                            Customer,
                            tenant_scope,
                        ),
                    )
                )
            ).scalars().first()
            if not customer:
                raise ValueError("Selected customer not found")
        else:
            customer = await LeadService._find_existing_customer(
                session,
                phone=phone,
                email=email,
                inn=inn,
                tenant_scope=tenant_scope,
            )

        if payload.customer_type:
            customer_type = CustomerType(payload.customer_type)
        elif inn or full_legal_name:
            customer_type = CustomerType.company
        else:
            customer_type = CustomerType.individual

        is_business_customer = is_business_customer_type(customer_type)
        customer_name = name or (full_legal_name if is_business_customer else None) or f"Лид #{lead.id}"
        customer_phone = phone or ""

        if customer is None:
            customer = Customer(
                tenant_id=tenant_scope.tenant_id,
                name=customer_name,
                phone=customer_phone,
                email=email,
                type=customer_type,
                signing_mode=signing_mode_for_customer_type(customer_type),
                inn=inn,
                full_legal_name=full_legal_name,
                legal_address=legal_address,
                iban=iban,
                bic=bic,
                bank_name=bank_name,
            )
            session.add(customer)
            await session.flush()
        else:
            if customer.tenant_id is None:
                customer.tenant_id = tenant_scope.tenant_id
            customer.name = customer_name
            if phone:
                customer.phone = phone
            if email:
                customer.email = email
            if inn:
                customer.inn = inn
            if full_legal_name:
                customer.full_legal_name = full_legal_name
            if legal_address:
                customer.legal_address = legal_address
            if iban:
                customer.iban = iban
            if bic:
                customer.bic = bic
            if bank_name:
                customer.bank_name = bank_name
            if payload.customer_type:
                customer.type = customer_type
                customer.signing_mode = signing_mode_for_customer_type(customer_type)
            elif customer_type == CustomerType.company:
                customer.type = CustomerType.company
                if customer.signing_mode == "self":
                    customer.signing_mode = "statutory_body"
            session.add(customer)
            await session.flush()

        order_comment = LeadService._clean_optional(payload.order_comment) or lead.request_text
        title_suffix = (order_comment or "").strip()
        selected_branch: Optional[CustomerBranch] = None
        if selected_customer_branch_id is not None:
            selected_branch = await session.get(CustomerBranch, int(selected_customer_branch_id))
            if not selected_branch:
                raise ValueError("Selected customer branch not found")
            if int(selected_branch.customer_id) != int(customer.id or 0):
                raise ValueError("Selected customer branch does not belong to selected customer")

        order_delivery_address = LeadService._clean_optional(payload.delivery_address)
        if not order_delivery_address and selected_branch:
            order_delivery_address = selected_branch.delivery_address

        order = Order(
            tenant_id=lead.tenant_id,
            storefront_id=lead.storefront_id,
            customer_id=customer.id,
            customer_branch_id=int(selected_branch.id) if selected_branch and selected_branch.id is not None else None,
            status=OrderStatus.NEW_LEAD,
            lead_source=LeadService._order_source_for_lead(lead),
            comment=order_comment,
            title=f"Лид #{lead.id}" if not title_suffix else f"Лид #{lead.id}: {title_suffix[:96]}",
            delivery_address=order_delivery_address,
            status_changed_at=datetime.now(),
        )
        session.add(order)
        await session.flush()

        lead.status = LeadStatus.qualified
        lead.converted_order_id = order.id
        lead.segment_hint = LeadService._normalize_segment_hint(
            inn=inn,
            explicit_hint=(
                LeadSegmentHint.b2b.value
                if is_business_customer_type(customer.type)
                else LeadSegmentHint.b2c.value
            ),
        )
        lead.loss_reason = None
        session.add(lead)

        await session.flush()
        await session.refresh(lead)

        return {
            "lead": LeadService._map_lead(lead),
            "customer_id": int(customer.id),
            "order_id": int(order.id),
            "order_created": True,
        }

    @staticmethod
    async def archive_expired_lost_leads(session: AsyncSession, older_than_days: int = 90) -> int:
        now = datetime.now()
        cutoff = now - timedelta(days=older_than_days)

        stmt = select(Lead).where(
            Lead.archived_at.is_(None),
            Lead.status.in_([LeadStatus.lost, LeadStatus.spam]),
            func.coalesce(Lead.updated_at, Lead.created_at) < cutoff,
        )
        result = await session.execute(stmt)
        leads = list(result.scalars().all())

        for lead in leads:
            lead.archived_at = now
            session.add(lead)

        if leads:
            await session.commit()

        return len(leads)
