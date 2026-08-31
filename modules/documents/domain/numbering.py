from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class DocumentNumberScope:
    tenant_id: int
    legal_entity_id: int
    document_type: str
    series: str
    period_key: str

    def normalized(self) -> "DocumentNumberScope":
        document_type = self.document_type.strip().lower()
        period_key = self.period_key.strip()
        series = self.series.strip()
        if self.tenant_id <= 0 or self.legal_entity_id <= 0:
            raise ValueError("Tenant and legal entity ids must be positive")
        if not document_type:
            raise ValueError("Document type is required")
        if not period_key:
            raise ValueError("Numbering period is required")
        return DocumentNumberScope(
            tenant_id=self.tenant_id,
            legal_entity_id=self.legal_entity_id,
            document_type=document_type,
            series=series,
            period_key=period_key,
        )


@dataclass(frozen=True, slots=True)
class EffectiveDocumentNumberPolicy:
    document_type: str
    series: str
    period_mode: str = "calendar_year"
    minimum_width: int = 3

    def normalized(self) -> "EffectiveDocumentNumberPolicy":
        document_type = str(self.document_type or "").strip().lower()
        series = str(self.series or "").strip()
        period_mode = str(self.period_mode or "").strip().lower()
        if not document_type:
            raise ValueError("Document type is required")
        if period_mode not in {"calendar_year", "continuous", "per_basis"}:
            raise ValueError("Unsupported document numbering period")
        if not 1 <= int(self.minimum_width) <= 12:
            raise ValueError("Document number width must be between 1 and 12")
        return EffectiveDocumentNumberPolicy(
            document_type=document_type,
            series=series,
            period_mode=period_mode,
            minimum_width=int(self.minimum_width),
        )

    def period_key(self, issued_on: date, *, basis_key: str | None = None) -> str:
        policy = self.normalized()
        if policy.period_mode == "calendar_year":
            return str(issued_on.year)
        if policy.period_mode == "continuous":
            return "all"
        normalized_basis = str(basis_key or "").strip().lower()
        # The persisted sequence and reservation contracts both use VARCHAR(32).
        # Reject an oversized basis key here instead of failing later at flush.
        if not normalized_basis or len(normalized_basis) > 32:
            raise ValueError("Basis is required for per-basis numbering")
        return normalized_basis


DEFAULT_NUMBER_POLICIES: dict[str, EffectiveDocumentNumberPolicy] = {
    "contract": EffectiveDocumentNumberPolicy("contract", "Д-"),
    "invoice": EffectiveDocumentNumberPolicy("invoice", "С-"),
    "invoice_offer": EffectiveDocumentNumberPolicy("invoice_offer", "СО-"),
    "offer": EffectiveDocumentNumberPolicy("offer", "КП-"),
    "act": EffectiveDocumentNumberPolicy("act", "А-"),
    "tn2": EffectiveDocumentNumberPolicy("tn2", "ТН-"),
    "ttn1": EffectiveDocumentNumberPolicy("ttn1", "ТТН-"),
    "b2c_supply_installation_act": EffectiveDocumentNumberPolicy(
        "b2c_supply_installation_act", "ЗА-"
    ),
    "b2c_customer_equipment_installation_act": EffectiveDocumentNumberPolicy(
        "b2c_customer_equipment_installation_act", "АУ-"
    ),
    "b2c_maintenance_repair_act": EffectiveDocumentNumberPolicy(
        "b2c_maintenance_repair_act", "АР-"
    ),
    "b2c_route_laying_act": EffectiveDocumentNumberPolicy(
        "b2c_route_laying_act", "ЗТ-"
    ),
}


def numbering_policy_key(document_type: str, business_role: str | None = None) -> str:
    normalized = str(document_type or "").strip().lower()
    if normalized == "invoice" and str(business_role or "").strip().lower() == "offer":
        return "invoice_offer"
    return normalized


def new_internal_reference() -> str:
    """Opaque CRM identity; unlike an official number it has no legal meaning."""

    return f"doc_{uuid4().hex}"
