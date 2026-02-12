from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import String, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Customer,
    CustomerType,
    Lead,
    LeadIntakeSource,
    LeadLossReason,
    LeadSegmentHint,
    LeadSource as OrderLeadSource,
    LeadStatus,
    Order,
    OrderStatus,
)
from schemas import Meta


class LeadService:
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
            "loss_reason": lead.loss_reason.value if hasattr(lead.loss_reason, "value") else lead.loss_reason,
            "next_followup_date": lead.next_followup_date,
            "archived_at": lead.archived_at,
            "converted_order_id": lead.converted_order_id,
            "created_at": lead.created_at,
            "updated_at": lead.updated_at,
        }

    @staticmethod
    async def create_lead(session: AsyncSession, payload: Any) -> Dict[str, Any]:
        request_text = (payload.request_text or "").strip()
        if not request_text:
            raise ValueError("request_text is required")

        inn = LeadService._clean_optional(payload.inn)
        segment_hint = LeadService._normalize_segment_hint(inn, payload.segment_hint)
        source = LeadIntakeSource(payload.source)

        lead = Lead(
            status=LeadStatus.new,
            source=source,
            segment_hint=segment_hint,
            name=LeadService._clean_optional(payload.name),
            phone=LeadService._clean_optional(payload.phone),
            email=LeadService._clean_optional(payload.email),
            inn=inn,
            company_name=LeadService._clean_optional(payload.company_name),
            request_text=request_text,
            next_followup_date=payload.next_followup_date,
        )
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
        return LeadService._map_lead(lead)

    @staticmethod
    async def list_leads(
        session: AsyncSession,
        page: int,
        limit: int,
        status: Optional[str] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
        overdue_only: bool = False,
        include_archived: bool = False,
        sort: str = "created_at_desc",
    ) -> Dict[str, Any]:
        stmt = select(Lead)
        count_stmt = select(func.count(Lead.id))

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
    async def update_lead(session: AsyncSession, lead_id: int, payload: Any) -> Optional[Dict[str, Any]]:
        lead = await session.get(Lead, lead_id)
        if not lead:
            return None

        fields_set = getattr(payload, "model_fields_set", None)
        if fields_set is None:
            fields_set = getattr(payload, "__fields_set__", set())

        explicit_segment_hint: Optional[str] = None
        should_recompute_segment = False

        if "status" in fields_set and payload.status is not None:
            lead.status = LeadStatus(payload.status)
        if "source" in fields_set and payload.source is not None:
            lead.source = LeadIntakeSource(payload.source)
        if "name" in fields_set:
            lead.name = LeadService._clean_optional(payload.name)
        if "phone" in fields_set:
            lead.phone = LeadService._clean_optional(payload.phone)
        if "email" in fields_set:
            lead.email = LeadService._clean_optional(payload.email)
        if "inn" in fields_set:
            lead.inn = LeadService._clean_optional(payload.inn)
            should_recompute_segment = True
        if "company_name" in fields_set:
            lead.company_name = LeadService._clean_optional(payload.company_name)
        if "request_text" in fields_set and payload.request_text is not None:
            request_text = payload.request_text.strip()
            if not request_text:
                raise ValueError("request_text cannot be empty")
            lead.request_text = request_text
        if "loss_reason" in fields_set:
            lead.loss_reason = LeadLossReason(payload.loss_reason) if payload.loss_reason else None
        if "next_followup_date" in fields_set:
            lead.next_followup_date = payload.next_followup_date
        if "archived_at" in fields_set:
            lead.archived_at = payload.archived_at
        if "segment_hint" in fields_set:
            explicit_segment_hint = payload.segment_hint
            should_recompute_segment = True

        if should_recompute_segment:
            lead.segment_hint = LeadService._normalize_segment_hint(lead.inn, explicit_segment_hint)

        session.add(lead)
        await session.commit()
        await session.refresh(lead)
        return LeadService._map_lead(lead)

    @staticmethod
    async def mark_lead_lost(session: AsyncSession, lead_id: int, payload: Any) -> Optional[Dict[str, Any]]:
        lead = await session.get(Lead, lead_id)
        if not lead:
            return None

        lead.status = LeadStatus(payload.status)
        lead.loss_reason = LeadLossReason(payload.loss_reason) if payload.loss_reason else (
            LeadLossReason.spam if lead.status == LeadStatus.spam else lead.loss_reason
        )
        lead.next_followup_date = None

        session.add(lead)
        await session.commit()
        await session.refresh(lead)
        return LeadService._map_lead(lead)

    @staticmethod
    async def _find_existing_customer(
        session: AsyncSession,
        phone: Optional[str],
        email: Optional[str],
        inn: Optional[str],
    ) -> Optional[Customer]:
        predicates = []
        if phone:
            predicates.append(Customer.phone == phone)
        if email:
            predicates.append(Customer.email == email)
        if inn:
            predicates.append(Customer.inn == inn)
        if not predicates:
            return None

        result = await session.execute(select(Customer).where(or_(*predicates)).order_by(Customer.created_at.asc()))
        customers = result.scalars().all()
        if not customers:
            return None

        if inn:
            for item in customers:
                if item.inn == inn:
                    return item
        if phone:
            for item in customers:
                if item.phone == phone:
                    return item
        if email:
            for item in customers:
                if item.email == email:
                    return item
        return customers[0]

    @staticmethod
    async def qualify_lead(session: AsyncSession, lead_id: int, payload: Any) -> Optional[Dict[str, Any]]:
        lead = await session.get(Lead, lead_id)
        if not lead:
            return None
        if lead.status in {LeadStatus.spam, LeadStatus.lost}:
            raise ValueError("Cannot qualify a lost/spam lead")

        name = LeadService._clean_optional(payload.name) or LeadService._clean_optional(lead.name)
        phone = LeadService._clean_optional(payload.phone) or LeadService._clean_optional(lead.phone)
        email = LeadService._clean_optional(payload.email) or LeadService._clean_optional(lead.email)
        inn = LeadService._clean_optional(payload.inn) or LeadService._clean_optional(lead.inn)
        full_legal_name = LeadService._clean_optional(payload.full_legal_name) or LeadService._clean_optional(lead.company_name)

        customer = await LeadService._find_existing_customer(session, phone=phone, email=email, inn=inn)

        if payload.customer_type:
            customer_type = CustomerType(payload.customer_type)
        elif inn or full_legal_name:
            customer_type = CustomerType.company
        else:
            customer_type = CustomerType.individual

        customer_name = name or (full_legal_name if customer_type == CustomerType.company else None) or f"Лид #{lead.id}"
        customer_phone = phone or ""

        if customer is None:
            customer = Customer(
                name=customer_name,
                phone=customer_phone,
                email=email,
                type=customer_type,
                inn=inn,
                full_legal_name=full_legal_name,
            )
            session.add(customer)
            await session.flush()
        else:
            customer.name = customer_name
            if phone:
                customer.phone = phone
            if email:
                customer.email = email
            if inn:
                customer.inn = inn
            if full_legal_name:
                customer.full_legal_name = full_legal_name
            if customer_type == CustomerType.company:
                customer.type = CustomerType.company
            session.add(customer)
            await session.flush()

        order_comment = LeadService._clean_optional(payload.order_comment) or lead.request_text
        title_suffix = (order_comment or "").strip()
        order = Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            lead_source=OrderLeadSource.MANAGER,
            comment=order_comment,
            title=f"Лид #{lead.id}" if not title_suffix else f"Лид #{lead.id}: {title_suffix[:96]}",
            delivery_address=LeadService._clean_optional(payload.delivery_address),
        )
        session.add(order)
        await session.flush()

        lead.status = LeadStatus.qualified
        lead.converted_order_id = order.id
        lead.segment_hint = LeadService._normalize_segment_hint(
            inn=inn,
            explicit_hint=LeadSegmentHint.b2b.value if customer.type == CustomerType.company else LeadSegmentHint.b2c.value,
        )
        lead.loss_reason = None
        session.add(lead)

        await session.commit()
        await session.refresh(lead)

        return {
            "lead": LeadService._map_lead(lead),
            "customer_id": int(customer.id),
            "order_id": int(order.id),
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
