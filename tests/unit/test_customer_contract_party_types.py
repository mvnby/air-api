from datetime import datetime

import pytest

from modules.documents.domain.customer_signing import CUSTOMER_POSITION_LINE, CUSTOMER_BASIS_LINE, CUSTOMER_NAME_LINE
from services.documents.standard import GeneralDocStrategy

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
    assert replacements["{{signer_name}}"] == ""


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
    assert replacements["{{signer_name}}"] == "Иванов Иван Иванович"
    order_replacements = GeneralDocStrategy(None, 1)._append_customer_variables({}, customer)
    assert order_replacements["{{signer_position}}"] == "директора"
    assert order_replacements["{{acting_basis}}"] == "Устава"
    assert order_replacements["{{signer_name}}"] == "Иванов Иван Иванович"


def test_individual_is_not_a_business_party() -> None:
    customer = Customer(
        tenant_id=1,
        name="Иван Иванов",
        phone="+375295912681",
        type=CustomerType.individual,
    )

    assert not CustomerContractService._is_business_customer(customer)


@pytest.mark.parametrize("position,basis", [(None, None), ("", ""), ("  ", "\t")])
def test_contract_and_order_documents_leave_handwriting_lines_for_unknown_facts(position, basis):
    customer = Customer(
        tenant_id=1, name="ООО Клиент", phone="", type=CustomerType.company,
        signer_position=position, acting_basis=basis,
    )
    expected = {"{{signer_position}}": CUSTOMER_POSITION_LINE, "{{acting_basis}}": CUSTOMER_BASIS_LINE, "{{signer_name}}": CUSTOMER_NAME_LINE}
    contract = CustomerContractService._build_replacements(customer, _contract())
    order = GeneralDocStrategy(None, 1)._append_customer_variables({}, customer)
    for values in (contract, order):
        assert {key: values[key] for key in expected} == expected
    assert customer.signer_position == position
    assert customer.acting_basis == basis


@pytest.mark.parametrize("party", [CustomerType.individual, CustomerType.individual_entrepreneur])
@pytest.mark.parametrize("mode", ["self", "power_of_attorney"])
def test_non_company_signing_does_not_request_organization_position(party, mode):
    customer = Customer(
        tenant_id=1, name="Иванов Иван Иванович", phone="", type=party,
        signing_mode=mode, signer_position="директора", acting_basis="",
    )
    for values in (
        CustomerContractService._build_replacements(customer, _contract()),
        GeneralDocStrategy(None, 1)._append_customer_variables({}, customer),
    ):
        assert values["{{signer_position}}"] == ""
        assert values["{{acting_basis}}"] == ("" if mode == "self" else CUSTOMER_BASIS_LINE)
        assert values["{{signer_name}}"] == ("" if mode == "self" else CUSTOMER_NAME_LINE)
