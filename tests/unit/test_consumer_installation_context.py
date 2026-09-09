from decimal import Decimal

import pytest
from pydantic import ValidationError

from modules.documents.api.schemas import ManagedDocumentDraftPayload
from modules.documents.application.installation_context import (
    STAGED_INSTALLATION_CONDITIONS,
    STAGED_INSTALLATION_FIELDS,
    build_installation_context,
    staged_template_is_supported,
)
from modules.documents.domain import ConsumerDocumentTerms


def build(amount, total="3140"):
    return build_installation_context(
        document_type="b2c_supply_installation_act",
        terms=ConsumerDocumentTerms(
            installation_two_stages=True, installation_first_stage_amount=amount,
        ),
        total=Decimal(total),
    )


def test_two_stage_payment_is_calculated_from_total_with_exact_kopecks():
    values, conditions = build("3000")
    assert values["installation.first_stage_amount"] == "3000.00"
    assert values["installation.remaining_amount"] == "140.00"
    assert "внутреннего блока" in values["installation.second_stage_works"]
    assert "после выполнения второго этапа" in values["installation.second_stage_due"]
    assert conditions == {"installation.two_stages": True, "installation.single_stage": False}
    assert build("3000.11", "3140.31")[0]["installation.remaining_amount"] == "140.20"


@pytest.mark.parametrize("outdoor_in_first", [True, False])
def test_outdoor_unit_moves_between_stages_without_changing_payment(outdoor_in_first):
    payload = ManagedDocumentDraftPayload(
        legal_entity_id=1, document_type="b2c_supply_installation_act", issue_date="2026-09-09",
        consumer_terms={
            "installation_two_stages": True,
            "installation_first_stage_amount": "3000",
            "installation_outdoor_unit_in_first_stage": outdoor_in_first,
        },
    )
    values, _ = build_installation_context(
        document_type=payload.document_type,
        terms=ConsumerDocumentTerms(**payload.consumer_terms.model_dump()),
        total=Decimal("3140"),
    )
    assert ("наружного" in values["installation.first_stage_works"]) is outdoor_in_first
    assert ("наружного" in values["installation.second_stage_works"]) is not outdoor_in_first
    assert "внутреннего" in values["installation.second_stage_works"]
    assert "пусконаладочные" in values["installation.second_stage_works"]
    assert values["installation.remaining_amount"] == "140.00"


def test_existing_staged_requests_keep_outdoor_unit_in_first_stage_by_default():
    payload = ManagedDocumentDraftPayload(
        legal_entity_id=1, document_type="b2c_supply_installation_act", issue_date="2026-09-09",
        consumer_terms={"installation_two_stages": True, "installation_first_stage_amount": "3000"},
    )
    assert payload.consumer_terms.installation_outdoor_unit_in_first_stage is True


@pytest.mark.parametrize("amount", [None, "", "NaN", "Infinity", "0", "-1", "3140", "3141", "1.001"])
def test_invalid_stage_payment_is_rejected(amount):
    with pytest.raises(ValueError):
        build(amount)


def test_single_stage_ignores_stale_payment_value():
    values, conditions = build_installation_context(
        document_type="b2c_supply_installation_act",
        terms=ConsumerDocumentTerms(installation_first_stage_amount="3000"),
        total=Decimal("3140"),
    )
    assert all(value == "" for value in values.values())
    assert conditions["installation.single_stage"] is True


def test_template_must_explicitly_support_both_branches_and_stage_terms():
    schema = {"fields": list(STAGED_INSTALLATION_FIELDS), "conditions": list(STAGED_INSTALLATION_CONDITIONS)}
    assert staged_template_is_supported(schema)
    assert not staged_template_is_supported({})
    assert not staged_template_is_supported({**schema, "fields": ["installation.first_stage_amount"]})


def test_other_b2c_acts_cannot_capture_staged_sale_terms():
    with pytest.raises(ValidationError, match="для продажи с монтажом"):
        ManagedDocumentDraftPayload(
            legal_entity_id=1, document_type="b2c_route_laying_act", issue_date="2026-09-09",
            consumer_terms={"installation_two_stages": True, "installation_first_stage_amount": "3000"},
        )
