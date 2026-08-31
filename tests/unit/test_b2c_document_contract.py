from datetime import date

import pytest

from modules.documents.api.schemas import (
    DocumentLegalEntityRequisites,
    ManagedDocumentDraftPayload,
)
from modules.documents.application.consumer_context import (
    ConsumerDocumentContextError,
    build_consumer_document_context,
)
from modules.documents.domain import (
    CONDITIONAL_FLAGS,
    ConsumerDocumentTerms,
    DEFAULT_NUMBER_POLICIES,
    SCALAR_PLACEHOLDERS,
    SUPPORTED_NATIVE_DOCUMENT_TYPES,
)


def test_b2c_document_types_and_consumer_terms_are_exposed_to_the_api():
    b2c_types = {
        "b2c_supply_installation_act",
        "b2c_customer_equipment_installation_act",
        "b2c_maintenance_repair_act",
        "b2c_route_laying_act",
    }

    assert b2c_types <= SUPPORTED_NATIVE_DOCUMENT_TYPES
    assert b2c_types <= DEFAULT_NUMBER_POLICIES.keys()
    payload = ManagedDocumentDraftPayload(
        legal_entity_id=1,
        document_type="b2c_route_laying_act",
        issue_date=date(2026, 8, 31),
        consumer_terms={
            "equipment_brand": "Midea",
            "goods_warranty_months": 48,
            "route_photo_fixation_performed": True,
            "route_ends_capped": True,
        },
    )

    assert payload.consumer_terms is not None
    assert payload.consumer_terms.goods_warranty_months == 48
    assert payload.consumer_terms.route_photo_fixation_performed is True


def test_b2c_placeholder_catalog_has_printable_toggle_states_and_default_warranty():
    placeholder_names = {item.name for item in SCALAR_PLACEHOLDERS}
    condition_names = {item.name for item in CONDITIONAL_FLAGS}

    assert {
        "route.photo_fixation_status",
        "route.pressure_test_status",
        "route.ends_capped_status",
    } <= placeholder_names
    assert {
        "route.photo_fixation_performed",
        "route.pressure_test_performed",
        "route.ends_capped",
    } <= condition_names
    assert DocumentLegalEntityRequisites().default_goods_warranty_months == 36


def test_supply_warranty_prefers_explicit_then_issuer_then_36_months():
    offer = {
        "offer_url": "https://mvn.by/offer",
        "offer_version": "1.0",
        "offer_published_on": "04.06.2026",
    }
    configured = build_consumer_document_context(
        document_type="b2c_supply_installation_act",
        terms=ConsumerDocumentTerms(),
        seller_requisites={**offer, "default_goods_warranty_months": "24"},
    )
    explicit = build_consumer_document_context(
        document_type="b2c_supply_installation_act",
        terms=ConsumerDocumentTerms(goods_warranty_months=48),
        seller_requisites={**offer, "default_goods_warranty_months": "24"},
    )
    fallback = build_consumer_document_context(
        document_type="b2c_supply_installation_act",
        terms=None,
        seller_requisites=offer,
    )

    assert configured.values["warranty.goods.months"] == "24"
    assert explicit.values["warranty.goods.months"] == "48"
    assert fallback.values["warranty.goods.months"] == "36"


def test_non_supply_b2c_documents_do_not_claim_equipment_warranty():
    context = build_consumer_document_context(
        document_type="b2c_maintenance_repair_act",
        terms=ConsumerDocumentTerms(goods_warranty_months=48),
        seller_requisites={
            "offer_url": "https://mvn.by/offer",
            "offer_version": "1.0",
            "offer_published_on": "04.06.2026",
            "default_goods_warranty_months": "24",
        },
    )

    assert context.values["warranty.goods.months"] == ""
    assert context.values["warranty.goods.terms"] == ""
    assert context.conditions["warranty.goods.present"] is False


def test_b2c_context_requires_a_versioned_public_offer():
    with pytest.raises(ConsumerDocumentContextError, match="публичную оферту"):
        build_consumer_document_context(
            document_type="b2c_supply_installation_act",
            terms=None,
            seller_requisites={},
        )


def test_b2b_payload_rejects_consumer_terms():
    with pytest.raises(ValueError, match="только для B2C"):
        ManagedDocumentDraftPayload(
            legal_entity_id=1,
            document_type="contract",
            issue_date=date(2026, 8, 31),
            consumer_terms={"goods_warranty_months": 36},
        )
