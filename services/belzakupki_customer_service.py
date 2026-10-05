"""Verify source party identities and apply explicitly reviewed CRM requisites."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import text

from core.input_validation import normalize_phone_digits
from models import Customer, Order
from models.common import CustomerType
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import ManagerOrderSourceApply, SourceCustomerDraft
from services.belarus_registry_service import fetch_registry_data
from services.customer_creation_service import CustomerAlreadyExistsError, CustomerCreationService
from services.customer_party_classifier import infer_customer_type_from_requisites
from services.tenant_entity_access_service import TenantEntityAccessService


async def enrich_registry(evidence) -> None:
    """Registry outages leave the document draft reviewable, without guessing."""
    drafts = [evidence.customer, *evidence.related_customers]
    unique = list(dict.fromkeys(draft.inn for draft in drafts if draft.inn))[:4]
    results = await asyncio.gather(*(fetch_registry_data(unp) for unp in unique))
    verified = {}
    for unp, result in zip(unique, results):
        row = result.get("row")
        if not isinstance(row, dict) or str(row.get("vunp") or "") != unp:
            evidence.warnings.append(f"Не удалось проверить УНП {unp} в реестре; проверьте реквизиты по источнику.")
            continue
        verified[unp] = row
    for draft in drafts:
        row = verified.get(draft.inn)
        if row is None:
            continue
        name = str(row.get("vnaimp") or "").strip()
        address = str(row.get("vpadres") or "").strip()
        if name:
            draft.name = name[:500]
            draft.type = infer_customer_type_from_requisites({"name": name, "inn": draft.inn}).value
        if address:
            draft.legal_address = address[:500]
        if draft is evidence.customer:
            if name:
                evidence.field_sources["customer.name"] = "Проверено по УНП в реестре"
                evidence.field_sources["customer.type"] = "Определено по реквизитам из реестра"
            if address:
                evidence.field_sources["customer.legal_address"] = "Проверено по УНП в реестре"


def _same_name(customer: Customer, draft: SourceCustomerDraft) -> bool:
    def key(value):
        return "".join(char for char in str(value or "").casefold() if char.isalnum())
    return key(draft.name) in {key(customer.name), key(customer.full_legal_name)} - {""}


async def apply_reviewed_customer(
    session: AsyncSession, *, order: Order, scope: TenantScope,
    payload: ManagerOrderSourceApply, evidence, applied: list[str],
) -> Customer | None:
    draft = payload.customer
    allowed_unps = {item.inn for item in [evidence.customer, *evidence.related_customers] if item.inn}
    if draft and draft.inn and allowed_unps and draft.inn not in allowed_unps:
        raise ValueError("Customer UNP does not match source UNP")
    if payload.customer_action == "skip":
        return None
    if payload.customer_action == "existing":
        if payload.customer_id is None:
            raise ValueError("customer_id is required")
        customer = await TenantEntityAccessService.get_customer(session, payload.customer_id, tenant_scope=scope)
        if customer is None:
            raise ValueError("Customer not found")
        if customer.inn and allowed_unps and customer.inn not in allowed_unps:
            raise ValueError("Customer UNP does not match source UNP")
        if draft is not None:
            if customer.inn and draft.inn and customer.inn != draft.inn:
                raise ValueError("Customer UNP does not match reviewed customer")
            if not customer.inn and draft.inn and not _same_name(customer, draft):
                raise ValueError("Проверьте УНП выбранного клиента в его карточке перед применением реквизитов.")
            changed = False
            for field in ("inn", "phone", "email", "legal_address", "bank_name", "bic", "iban"):
                value = getattr(draft, field)
                if not getattr(customer, field) and value:
                    setattr(customer, field, value)
                    changed = True
            if changed:
                applied.append("customer_requisites")
        return customer
    if draft is None or not (draft.name or "").strip():
        raise ValueError("Customer name is required")
    identity = draft.inn or normalize_phone_digits(draft.phone or "") or (draft.email or "").strip().lower()
    if identity:
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
                              {"lock_key": f"belzakupki-customer:{scope.tenant_id}:{identity}"})
    duplicate = await CustomerCreationService._find_duplicate(
        session, phone=draft.phone, email=draft.email, inn=draft.inn, tenant_scope=scope,
    )
    if duplicate is not None:
        existing, fields = duplicate
        raise CustomerAlreadyExistsError(customer_id=int(existing.id or 0), customer_name=existing.name, matched_fields=fields)
    try:
        party_type = CustomerType(draft.type)
    except ValueError:
        raise ValueError("Invalid customer type") from None
    customer = Customer(
        tenant_id=scope.tenant_id, name=draft.name.strip(), phone=draft.phone or "", email=draft.email,
        type=party_type, inn=draft.inn, full_legal_name=draft.name if party_type == CustomerType.company else None,
        legal_address=draft.legal_address, bank_name=draft.bank_name, bic=draft.bic, iban=draft.iban,
        signing_mode="statutory_body" if party_type == CustomerType.company else "self",
    )
    session.add(customer)
    await session.flush()
    applied.append("customer_created")
    return customer
