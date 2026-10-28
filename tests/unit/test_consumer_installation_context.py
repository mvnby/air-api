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
    assert "после выполнения и приемки второго этапа" in values["installation.second_stage_due"]
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


@pytest.mark.parametrize("amount", ["", "NaN", "Infinity", "0", "-1", "3140", "3141", "1.001"])
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
    with pytest.raises(ValidationError, match="для поставки с монтажом"):
        ManagedDocumentDraftPayload(
            legal_entity_id=1, document_type="b2c_route_laying_act", issue_date="2026-09-09",
            consumer_terms={"installation_two_stages": True, "installation_first_stage_amount": "3000"},
        )


@pytest.mark.parametrize("document_type", ["b2c_supply_installation_act", "b2c_customer_equipment_installation_act"])
@pytest.mark.parametrize("outdoor_first,remaining", [(True, "300.00"), (False, "600.00")])
def test_default_remainder_is_per_conditioner_for_both_installation_documents(document_type, outdoor_first, remaining):
    payload = ManagedDocumentDraftPayload(
        legal_entity_id=1, document_type=document_type, issue_date="2026-10-28",
        consumer_terms={"installation_two_stages": True, "installation_unit_count": 3,
                        "installation_outdoor_unit_in_first_stage": outdoor_first},
    )
    values, _ = build_installation_context(
        document_type=document_type, terms=ConsumerDocumentTerms(**payload.consumer_terms.model_dump()),
        total=Decimal("3900"),
    )
    assert values["installation.remaining_amount"] == remaining
    assert Decimal(values["installation.first_stage_amount"]) + Decimal(remaining) == Decimal("3900")


def test_custom_400_remainder_and_work_descriptions_override_defaults():
    values, _ = build_installation_context(
        document_type="b2c_customer_equipment_installation_act",
        terms=ConsumerDocumentTerms(
            installation_two_stages=True, installation_unit_count=3,
            installation_remaining_amount="400.00",
            installation_first_stage_works="Подготовка трех трасс и монтаж наружных блоков.",
            installation_second_stage_works="Монтаж трех внутренних блоков и пусконаладка.",
            installation_second_stage_due="По готовности помещений; оплата после приемки.",
        ), total=Decimal("3900"),
    )
    assert values["installation.first_stage_amount"] == "3500.00"
    assert values["installation.remaining_amount"] == "400.00"
    assert values["installation.first_stage_works"] == "Подготовка трех трасс и монтаж наружных блоков."
    assert values["installation.second_stage_works"] == "Монтаж трех внутренних блоков и пусконаладка."
    assert values["installation.second_stage_due"] == "По готовности помещений; оплата после приемки."


def test_server_rejects_stage_amounts_that_do_not_sum_to_selected_proposal():
    with pytest.raises(ValueError, match="Суммы этапов"):
        build_installation_context(
            document_type="b2c_customer_equipment_installation_act",
            terms=ConsumerDocumentTerms(installation_two_stages=True,
                installation_first_stage_amount="3500", installation_remaining_amount="300"),
            total=Decimal("3900"),
        )


@pytest.mark.parametrize("count", [0, -1, 1001, 1.5])
def test_api_rejects_invalid_installation_counts(count):
    with pytest.raises(ValidationError):
        ManagedDocumentDraftPayload(legal_entity_id=1, document_type="b2c_customer_equipment_installation_act",
            issue_date="2026-10-28", consumer_terms={"installation_two_stages": True, "installation_unit_count": count})


def test_default_remainder_cannot_exceed_the_order_total():
    with pytest.raises(ValueError, match="меньше общей суммы"):
        build_installation_context(document_type="b2c_customer_equipment_installation_act",
            terms=ConsumerDocumentTerms(installation_two_stages=True, installation_unit_count=3), total=Decimal("300"))


def test_empty_work_description_is_not_silently_replaced_with_a_preset():
    with pytest.raises(ValueError, match="состав работ"):
        build_installation_context(document_type="b2c_customer_equipment_installation_act",
            terms=ConsumerDocumentTerms(installation_two_stages=True, installation_first_stage_works="  "), total=Decimal("3900"))
