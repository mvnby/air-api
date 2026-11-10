from decimal import Decimal
import pytest
from pydantic import ValidationError
from modules.documents.domain.contract_amendment import ContractAmendmentTerms


def test_fractional_work_uses_half_up_cents_like_rendered_commercial_row():
    terms = ContractAmendmentTerms(
        works=[
            dict(
                title="Тестовая работа",
                quantity="0.5",
                unit="компл.",
                unit_price="0.29",
            )
        ]
    )
    assert terms.amount == Decimal("0.15")
    with pytest.raises(ValidationError, match="больше нуля"):
        ContractAmendmentTerms(
            works=[
                dict(
                    title="Тестовая работа",
                    quantity="0.001",
                    unit="м",
                    unit_price="0.01",
                )
            ]
        )
