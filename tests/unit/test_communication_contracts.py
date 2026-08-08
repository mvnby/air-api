from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from services.communications.contracts import (
    IntegrationEventEnvelopeV1,
    PublicContactLeadCreatedPayloadV1,
    PublicOrderCreatedPayloadV1,
    PublicOrderCustomerSnapshotV1,
    PublicOrderProductLineSnapshotV1,
)


def test_versioned_public_order_payload_is_bounded_and_json_safe():
    payload = PublicOrderCreatedPayloadV1(
        order_id=41,
        status="negotiation",
        customer=PublicOrderCustomerSnapshotV1(
            name="Иван",
            phone="+375291112233",
            address="Минск " + "А" * 490,
        ),
        comment="К" * 2000,
        total_amount=Decimal("1280.50"),
        product_lines=[
            PublicOrderProductLineSnapshotV1(
                product_id=7,
                title="TCL BreezeIN",
                quantity=1,
                unit_price=Decimal("1280.50"),
            )
        ],
    )

    dumped = payload.model_dump(mode="json")

    assert dumped["total_amount"] == "1280.50"
    assert dumped["currency"] == "BYN"
    assert dumped["product_lines"][0]["product_id"] == 7


def test_public_order_payload_accepts_storefront_currency_and_rejects_invalid_code():
    payload = PublicOrderCreatedPayloadV1(
        order_id=42,
        status="negotiation",
        customer=PublicOrderCustomerSnapshotV1(
            name="Tenant customer",
            phone="+375291112233",
        ),
        total_amount=Decimal("4200"),
        currency="EUR",
    )

    assert payload.currency == "EUR"
    with pytest.raises(ValidationError):
        PublicOrderCreatedPayloadV1(
            order_id=43,
            status="negotiation",
            customer=PublicOrderCustomerSnapshotV1(
                name="Tenant customer",
                phone="+375291112233",
            ),
            total_amount=Decimal("4200"),
            currency="eur",
        )


def test_contact_lead_contract_matches_public_ingress_bounds():
    payload = PublicContactLeadCreatedPayloadV1(
        lead_id=12,
        status="new",
        name="Иван",
        phone="+375291112233",
        address="А" * 500,
        message="М" * 2000,
    )

    assert len(payload.address or "") == 500
    assert len(payload.message or "") == 2000

    with pytest.raises(ValidationError):
        PublicContactLeadCreatedPayloadV1(
            lead_id=12,
            status="new",
            name="Иван",
            phone="+375291112233",
            message="М" * 2001,
        )


def test_event_envelope_requires_timezone_and_rejects_unknown_fields():
    base = {
        "event_id": "a" * 32,
        "event_type": "crm.public_order.created",
        "aggregate_type": "order",
        "aggregate_id": "41",
        "payload": {"order_id": 41},
    }

    with pytest.raises(ValidationError, match="timezone"):
        IntegrationEventEnvelopeV1(
            **base,
            occurred_at=datetime(2026, 7, 13, 12, 0, 0),
        )

    with pytest.raises(ValidationError, match="Extra inputs"):
        IntegrationEventEnvelopeV1(
            **base,
            occurred_at=datetime.now(timezone.utc),
            unexpected="not allowed",
        )
