"""Customer ownership and qualification mutations for Manager order updates."""

from typing import Any, Optional

from sqlmodel import select
from sqlalchemy.orm.attributes import flag_modified

from models import Customer, CustomerBranch, CustomerContract
from services.customer_party import customer_type_from_value, signing_mode_for_customer_type
from services.customer_contract_service import CustomerContractService
from services.order_service import OrderService
from services.order_update.context import OrderUpdateContext
from services.tenant_scope_service import tenant_scope_clause


CUSTOMER_FIELD_MAP = {
    "customer_name": "name",
    "customer_phone": "phone",
    "customer_email": "email",
    "customer_type": "type",
    "customer_inn": "inn",
    "customer_full_legal_name": "full_legal_name",
    "customer_legal_address": "legal_address",
    "customer_bank_name": "bank_name",
    "customer_bic": "bic",
    "customer_iban": "iban",
}

CRITICAL_CUSTOMER_FIELDS = {
    "customer_inn": "УНП",
    "customer_iban": "IBAN",
    "customer_bic": "BIC",
    "customer_bank_name": "Банк",
}

QUALIFICATION_META_FIELDS = {
    "object_type": "object_type",
    "service_type": "service_type",
    "equipment_class": "equipment_class",
    "marketing_source": "marketing_source",
    "no_answer_at": "no_answer_at",
}


async def apply_customer_fields(context: OrderUpdateContext) -> None:
    customer_id_changed = await _apply_customer_link(context)
    await _clear_stale_customer_children(context, customer_id_changed)
    await _apply_customer_branch(context)
    await _apply_customer_contract(context)
    await _update_linked_customer(context)
    _apply_customer_type_hint(context)
    _apply_qualification_meta(context)

    context.current_workflow_type = OrderService._normalize_workflow_type(
        getattr(context.order, "workflow_type", None)
    )
    if context.current_workflow_type == "repair":
        OrderService._ensure_repair_meta_defaults(context.order)
        flag_modified(context.order, "technical_meta")


async def _apply_customer_link(context: OrderUpdateContext) -> bool:
    order = context.order
    payload = context.payload
    if "customer_id" not in context.fields_set or payload.customer_id is None:
        return False
    if order.customer_id == payload.customer_id:
        return False

    new_customer = (
        await context.session.execute(
            select(Customer).where(
                Customer.id == payload.customer_id,
                tenant_scope_clause(Customer, context.tenant_scope),
            )
        )
    ).scalars().first()
    if not new_customer:
        raise ValueError("Customer not found")

    order.customer_id = payload.customer_id
    linked_customer_type = (
        new_customer.type.value
        if hasattr(new_customer.type, "value")
        else str(new_customer.type or "")
    )
    if linked_customer_type in {"individual", "individual_entrepreneur", "company"}:
        order.technical_meta = dict(order.technical_meta or {})
        order.technical_meta["lead_customer_type_known"] = True
        order.technical_meta["lead_customer_type"] = linked_customer_type
        flag_modified(order, "technical_meta")
    return True


async def _clear_stale_customer_children(
    context: OrderUpdateContext,
    customer_id_changed: bool,
) -> None:
    if not customer_id_changed:
        return

    order = context.order
    if (
        "customer_branch_id" not in context.fields_set
        and order.customer_branch_id is not None
    ):
        linked_branch = await context.session.get(
            CustomerBranch,
            order.customer_branch_id,
        )
        if (
            linked_branch
            and int(linked_branch.customer_id) != int(order.customer_id or 0)
        ):
            order.customer_branch_id = None
    if (
        "customer_contract_id" not in context.fields_set
        and order.customer_contract_id is not None
    ):
        linked_contract = await context.session.get(
            CustomerContract,
            order.customer_contract_id,
        )
        if (
            linked_contract
            and int(linked_contract.customer_id) != int(order.customer_id or 0)
        ):
            order.customer_contract_id = None
            order.customer_contract = None


async def _apply_customer_branch(context: OrderUpdateContext) -> None:
    if "customer_branch_id" not in context.fields_set:
        return

    order = context.order
    branch_id = context.payload.customer_branch_id
    if branch_id is None:
        order.customer_branch_id = None
        return
    if order.customer_id is None:
        raise ValueError("Cannot set customer branch without customer")

    branch = await context.session.get(CustomerBranch, branch_id)
    if not branch:
        raise ValueError("Customer branch not found")
    if int(branch.customer_id) != int(order.customer_id):
        raise ValueError("Customer branch does not belong to selected customer")
    order.customer_branch_id = int(branch.id)


async def _apply_customer_contract(context: OrderUpdateContext) -> None:
    if "customer_contract_id" not in context.fields_set:
        return

    order = context.order
    contract_id = context.payload.customer_contract_id
    if contract_id is None:
        order.customer_contract_id = None
        order.customer_contract = None
        return
    if order.customer_id is None:
        raise ValueError("Cannot set customer contract without customer")

    contract = await context.session.get(CustomerContract, contract_id)
    if not contract:
        raise ValueError("Customer contract not found")
    if int(contract.customer_id) != int(order.customer_id):
        raise ValueError("Customer contract does not belong to selected customer")
    if contract.status != CustomerContractService.ACTIVE_STATUS:
        raise ValueError("Customer contract is not active")
    order.customer_contract_id = int(contract.id)
    order.customer_contract = contract


async def _update_linked_customer(context: OrderUpdateContext) -> None:
    requested_fields = [
        field for field in CUSTOMER_FIELD_MAP if field in context.fields_set
    ]
    if not requested_fields or not context.order.customer_id:
        return

    customer = (
        await context.session.execute(
            select(Customer).where(
                Customer.id == context.order.customer_id,
                tenant_scope_clause(Customer, context.tenant_scope),
            )
        )
    ).scalars().first()
    if not customer:
        return

    critical_changes = []
    for field_name, label in CRITICAL_CUSTOMER_FIELDS.items():
        if field_name not in requested_fields:
            continue
        attr_name = CUSTOMER_FIELD_MAP[field_name]
        incoming = _clean_optional(getattr(context.payload, field_name, None))
        existing = _clean_optional(getattr(customer, attr_name, None))
        if existing and incoming and existing != incoming:
            critical_changes.append(label)

    if critical_changes and not bool(
        getattr(context.payload, "confirm_critical_customer_changes", False)
    ):
        raise ValueError(
            "Critical customer requisites change requires confirmation: "
            + ", ".join(critical_changes)
        )

    for field_name in requested_fields:
        if field_name == "customer_type":
            customer_type = customer_type_from_value(
                getattr(context.payload, field_name, None)
            )
            customer.type = customer_type
            customer.signing_mode = signing_mode_for_customer_type(customer_type)
            continue
        setattr(
            customer,
            CUSTOMER_FIELD_MAP[field_name],
            _clean_optional(getattr(context.payload, field_name, None)),
        )
    context.session.add(customer)


def _apply_customer_type_hint(context: OrderUpdateContext) -> None:
    incoming_customer_type = str(
        getattr(context.payload, "customer_type", "") or ""
    ).strip()
    if (
        "customer_type" in context.fields_set
        and incoming_customer_type in {"individual", "individual_entrepreneur", "company"}
    ):
        context.order.technical_meta = dict(context.order.technical_meta or {})
        context.order.technical_meta["lead_customer_type_known"] = True
        context.order.technical_meta["lead_customer_type"] = incoming_customer_type
        flag_modified(context.order, "technical_meta")


def _apply_qualification_meta(context: OrderUpdateContext) -> None:
    requested_fields = [
        field for field in QUALIFICATION_META_FIELDS if field in context.fields_set
    ]
    if not requested_fields:
        return

    new_meta = dict(context.order.technical_meta or {})
    for field_name in requested_fields:
        value = getattr(context.payload, field_name, None)
        if value is None:
            continue
        new_meta[QUALIFICATION_META_FIELDS[field_name]] = value
        if field_name == "service_type" and "workflow_type" not in context.fields_set:
            context.order.workflow_type = OrderService._workflow_type_from_service_type(
                value,
                context.order.workflow_type,
            )
    context.order.technical_meta = new_meta
    flag_modified(context.order, "technical_meta")


def _clean_optional(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
