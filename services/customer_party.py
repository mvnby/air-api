"""Customer party-type rules shared by order creation and qualification."""

from typing import Any

from models import CustomerType


BUSINESS_CUSTOMER_TYPES = frozenset(
    {CustomerType.company, CustomerType.individual_entrepreneur}
)


def customer_type_from_value(value: Any) -> CustomerType:
    if isinstance(value, CustomerType):
        return value
    try:
        return CustomerType(str(value or "").strip())
    except ValueError:
        return CustomerType.individual


def signing_mode_for_customer_type(customer_type: CustomerType) -> str:
    return "statutory_body" if customer_type == CustomerType.company else "self"


def is_business_customer_type(value: Any) -> bool:
    return customer_type_from_value(value) in BUSINESS_CUSTOMER_TYPES


def valid_signing_modes_for_customer_type(value: Any) -> frozenset[str]:
    customer_type = customer_type_from_value(value)
    if customer_type == CustomerType.company:
        return frozenset({"statutory_body", "power_of_attorney"})
    return frozenset({"self", "power_of_attorney"})
