import pytest

from models import CustomerType
from modules.documents.domain.party import (
    INDIVIDUAL,
    INDIVIDUAL_ENTREPRENEUR,
    ORGANIZATION,
    customer_document_entity_type,
)


@pytest.mark.parametrize(
    ("customer_type", "name", "full_legal_name", "expected"),
    (
        (CustomerType.company, "Иван Иванов", None, ORGANIZATION),
        (CustomerType.individual_entrepreneur, "ООО Тест", None, INDIVIDUAL_ENTREPRENEUR),
        (
            CustomerType.individual,
            "ОДО «Термотехника»",
            "Общество с дополнительной ответственностью «Термотехника»",
            ORGANIZATION,
        ),
        (
            CustomerType.individual,
            "ИП Янулевич Дмитрий Викторович",
            None,
            INDIVIDUAL_ENTREPRENEUR,
        ),
        (CustomerType.individual, "Иван Иванов", None, INDIVIDUAL),
    ),
)
def test_customer_document_entity_type_preserves_explicit_type_and_repairs_legacy_identity(
    customer_type, name, full_legal_name, expected
) -> None:
    assert (
        customer_document_entity_type(
            customer_type,
            name=name,
            full_legal_name=full_legal_name,
        )
        == expected
    )


def test_customer_document_entity_type_uses_business_requisites_only_for_missing_type() -> None:
    requisites = {
        "inn": "300566486",
        "legal_address": "г. Витебск, ул. Тестовая, 1",
        "iban": "BY93BAPB3013W29470010000",
        "bic": "BAPBBY2X",
    }

    assert customer_document_entity_type(None, **requisites) == ORGANIZATION
    assert (
        customer_document_entity_type(CustomerType.individual, **requisites)
        == INDIVIDUAL
    )
