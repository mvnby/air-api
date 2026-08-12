import pytest

from models.supplier import ProductSupplierMapping
from services.supplier_offer_mapping_service import (
    SupplierOfferMappingConflictError,
    SupplierOfferMappingService,
)


def test_expected_mapping_state_requires_paired_ids():
    with pytest.raises(SupplierOfferMappingConflictError, match="provided together"):
        SupplierOfferMappingService._validate_expected_state(
            mapping=None,
            expected_mapping_id=10,
            expected_product_id=None,
        )


def test_expected_mapping_state_rejects_stale_product():
    mapping = ProductSupplierMapping(
        id=10,
        product_id=20,
        supplier_id=30,
        external_id="SKU",
        is_active=True,
    )

    with pytest.raises(SupplierOfferMappingConflictError, match="changed concurrently"):
        SupplierOfferMappingService._validate_expected_state(
            mapping=mapping,
            expected_mapping_id=10,
            expected_product_id=21,
        )


def test_expected_mapping_state_accepts_exact_active_mapping():
    mapping = ProductSupplierMapping(
        id=10,
        product_id=20,
        supplier_id=30,
        external_id="SKU",
        is_active=True,
    )

    SupplierOfferMappingService._validate_expected_state(
        mapping=mapping,
        expected_mapping_id=10,
        expected_product_id=20,
    )
