"""Factual projections for incoming Order cards without source-side changes."""

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Optional

from models import Order, LeadSource
from schemas_leads_inbox import LeadsInboxArchiveResponse, LeadsInboxItemResponse


class LeadsInboxProjection:
    @staticmethod
    def _clean_order_title(raw):
        return " ".join(str(raw or "").split()) or None

    @staticmethod
    def number(value):
        try:
            parsed = float(value)
            return parsed if math.isfinite(parsed) and parsed >= 0 else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def item(cls, order, *, state=None, read=None, attachment_count=0,
             no_answer_count=0, no_answer_at=None, auto_archive_enabled=False):
        from services.order_commercial_terms_service import commercial_terms_summary
        from services.leads_inbox_expiry_service import LeadsInboxExpiryService

        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        provider = meta.get("belzakupki")
        provider = provider if isinstance(provider, dict) else {}
        tender_meta = provider.get("tender")
        tender_meta = tender_meta if isinstance(tender_meta, dict) else {}
        enrichment = provider.get("enrichment")
        enrichment = enrichment if isinstance(enrichment, dict) else {}
        tender = cls._lead_inbox_tender(order)
        is_read = bool(read and read.is_read)
        archive = None
        if order.linked_order_id:
            archive = LeadsInboxArchiveResponse(outcome="linked", archived_at=order.linked_at, actor=order.linked_by)
        elif state and state.archived_at:
            archive = LeadsInboxArchiveResponse(outcome=state.outcome, reason=state.reason,
                note=state.note, archived_at=state.archived_at, actor=state.archived_by)
        elif order.status == "closed" and order.closing_result == "lost":
            archive = LeadsInboxArchiveResponse(outcome="legacy_lost", note=order.reject_reason)
        active = order.status == "new_lead" and order.linked_order_id is None and archive is None
        trusted_deadline = LeadsInboxExpiryService.trusted_deadline(order)
        suppressed_deadline = state.restored_deadline_at if state else None
        auto_archive_at = None
        if auto_archive_enabled and active and trusted_deadline and suppressed_deadline != trusted_deadline:
            auto_archive_at = trusted_deadline + timedelta(hours=24)
        title = (cls._clean_order_title(meta.get("email_subject")) or cls._clean_order_title(tender_meta.get("title"))
                 or cls._clean_order_title(order.title))
        summary = cls._clean_order_title(enrichment.get("work_summary") or meta.get("work_summary") or tender_meta.get("summary"))
        if not summary and order.lead_source != LeadSource.BELZAKUPKI:
            summary = cls._clean_order_title(order.comment)
        return LeadsInboxItemResponse(
            id=order.id, status="linked" if order.linked_order_id else getattr(order.status, "value", order.status),
            is_new=active and not is_read, is_read=is_read, read_at=read.read_at if read else None,
            source_kind="tender" if tender or order.lead_source == LeadSource.BELZAKUPKI else "customer_request",
            title=title, summary=summary[:500] if summary else None,
            budget_amount=cls.number(tender_meta.get("estimated_value") if order.lead_source == LeadSource.BELZAKUPKI else meta.get("budget_amount")),
            budget_currency=cls._clean_order_title(tender_meta.get("currency") if order.lead_source == LeadSource.BELZAKUPKI else meta.get("budget_currency")),
            quantity=cls.number(tender_meta.get("quantity") if order.lead_source == LeadSource.BELZAKUPKI else meta.get("quantity")),
            location=cls._clean_order_title(order.delivery_address or tender_meta.get("location") or meta.get("location")),
            deadline_at=tender.deadline_at if tender else None, archive=archive, auto_archive_at=auto_archive_at,
            linked_order_id=order.linked_order_id, customer_id=order.customer_id,
            customer_name=cls._lead_inbox_customer_name(order),
            phone=order.customer.phone if order.customer else None,
            email=order.customer.email if order.customer else None,
            source=getattr(order.lead_source, "value", order.lead_source) if order.lead_source else None, comment=order.comment,
            no_answer_at=no_answer_at or cls._parse_lead_inbox_datetime(meta.get("no_answer_at")),
            no_answer_count=no_answer_count,
            next_followup_at=(order.next_followup_date.replace(tzinfo=timezone.utc)
                              if order.next_followup_date and order.next_followup_date.tzinfo is None
                              else order.next_followup_date),
            source_created_at=cls._extract_email_source_created_at(order), created_at=order.created_at,
            customer_type=cls._lead_inbox_customer_type(order),
            customer_inn=order.customer.inn if order.customer else None,
            customer_full_legal_name=order.customer.full_legal_name if order.customer else None,
            customer_delivery_address=order.delivery_address,
            object_type=cls._lead_inbox_meta_text(order, "object_type"),
            service_type=cls._lead_inbox_meta_text(order, "service_type"),
            equipment_class=cls._lead_inbox_meta_text(order, "equipment_class"),
            marketing_source=cls._lead_inbox_meta_text(order, "marketing_source"),
            attachment_count=attachment_count, tender=tender,
            commercial_terms_summary=commercial_terms_summary(order),
        )

    @staticmethod
    def _parse_lead_inbox_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed

    @staticmethod
    def _extract_email_source_created_at(order: Order) -> Optional[datetime]:
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        parsed = LeadsInboxProjection._parse_lead_inbox_datetime(meta.get("email_date"))
        if parsed:
            return parsed

        marker = "Дата письма:"
        comment = order.comment or ""
        marker_index = comment.find(marker)
        if marker_index < 0:
            return None
        raw_line = comment[marker_index + len(marker):].strip().splitlines()[0].strip()
        return LeadsInboxProjection._parse_lead_inbox_datetime(raw_line)

    @staticmethod
    def _lead_inbox_customer_type(order: Order) -> Optional[str]:
        customer = order.customer
        if not customer:
            return None

        customer_type = customer.type.value if hasattr(customer.type, "value") else str(customer.type or "")
        if customer_type in {"individual_entrepreneur", "company"}:
            return customer_type

        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        raw_meta_type = str(meta.get("lead_customer_type") or "").strip()
        if (
            raw_meta_type in {"individual", "individual_entrepreneur", "company"}
            and meta.get("lead_customer_type_known") is True
        ):
            return raw_meta_type
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
    def _lead_inbox_customer_name(order: Order) -> Optional[str]:
        if order.customer:
            return LeadsInboxProjection._clean_order_title(order.customer.name)

        source = (
            order.lead_source.value
            if hasattr(order.lead_source, "value")
            else str(order.lead_source or "")
        )
        if source != LeadSource.BELZAKUPKI.value:
            return None

        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        source_meta = meta.get("belzakupki")
        tender = source_meta.get("tender") if isinstance(source_meta, dict) else None
        if not isinstance(tender, dict):
            return None
        return LeadsInboxProjection._clean_order_title(tender.get("customer_name"))

    @staticmethod
    def _lead_inbox_tender(order: Order):
        from schemas import LeadsInboxTenderResponse

        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        confirmed = meta.get("inbox_tender")
        if (order.lead_source == LeadSource.EMAIL and isinstance(confirmed, dict)
                and confirmed.get("confirmed") is True and confirmed.get("is_tender") is True):
            return LeadsInboxTenderResponse(source="email", url=confirmed.get("source_url"),
                deadline_at=LeadsInboxProjection._parse_lead_inbox_datetime(confirmed.get("deadline_at")),
                reason="Закупка подтверждена менеджером")
        if order.lead_source != LeadSource.BELZAKUPKI:
            return None
        source_meta = meta.get("belzakupki")
        if not isinstance(source_meta, dict):
            return None
        tender = source_meta.get("tender")
        if not isinstance(tender, dict):
            return None
        matches = source_meta.get("matches")
        match = next(
            (value for _, value in sorted(matches.items(), key=lambda pair: str(pair[0])) if isinstance(value, dict)),
            {},
        ) if isinstance(matches, dict) else {}
        profile = match.get("profile") if isinstance(match.get("profile"), dict) else {}
        raw_deadline = tender.get("deadline_at") if tender.get("deadline_kind", "submission") == "submission" else None
        try:
            deadline = datetime.fromisoformat(str(raw_deadline).replace("Z", "+00:00")) if raw_deadline else None
        except ValueError:
            deadline = None
        return LeadsInboxTenderResponse(
            source=str(tender.get("source") or "").strip() or None,
            url=str(tender.get("url") or "").strip() or None,
            deadline_at=deadline,
            reason=str(match.get("reason") or "").strip() or None,
            profile_name=str(profile.get("name") or "").strip() or None,
        )
