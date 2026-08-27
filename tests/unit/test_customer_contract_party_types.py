from datetime import datetime

from models import Customer, CustomerContract, CustomerType
from services.customer_contract_service import CustomerContractService


def _contract() -> CustomerContract:
    return CustomerContract(
        customer_id=1,
        number="ОД-2026-001",
        valid_from=datetime(2026, 8, 27),
        valid_until=datetime(2027, 8, 27),
    )


def test_individual_entrepreneur_is_a_business_party_and_signs_personally() -> None:
    customer = Customer(
        tenant_id=1,
        name="ИП Янулевич",
        phone="+375295912681",
        type=CustomerType.individual_entrepreneur,
        full_legal_name="Индивидуальный предприниматель Янулевич Дмитрий Викторович",
        signing_mode="self",
    )

    replacements = CustomerContractService._build_replacements(customer, _contract())

    assert CustomerContractService._is_business_customer(customer)
    assert replacements["{{client_name}}"] == customer.full_legal_name
    assert replacements["{{signer_position}}"] == ""
    assert replacements["{{acting_basis}}"] == ""


def test_company_keeps_representative_requisites() -> None:
    customer = Customer(
        tenant_id=1,
        name="ООО МВН",
        phone="+375295912681",
        type=CustomerType.company,
        signer_position="директора",
        signer_name="Иванов Иван Иванович",
        acting_basis="Устава",
        signing_mode="statutory_body",
    )

    replacements = CustomerContractService._build_replacements(customer, _contract())

    assert CustomerContractService._is_business_customer(customer)
    assert replacements["{{signer_position}}"] == "директора"
    assert replacements["{{acting_basis}}"] == "Устава"


def test_individual_is_not_a_business_party() -> None:
    customer = Customer(
        tenant_id=1,
        name="Иван Иванов",
        phone="+375295912681",
        type=CustomerType.individual,
    )

    assert not CustomerContractService._is_business_customer(customer)
