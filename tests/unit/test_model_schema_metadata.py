from sqlalchemy import Enum, String, UniqueConstraint
from sqlmodel import SQLModel

import models  # noqa: F401


def test_required_model_columns_match_database_nullability():
    required_columns = {
        "brand_feature": ("aliases",),
        "customer_equipment": ("equipment_type", "equipment_source"),
        "equipment_component": ("component_type",),
        "equipment_service_history": ("event_type",),
        "order": ("status", "negotiation_status", "execution_status"),
        "order_proposal": ("status",),
        "product_series": (
            "gallery_images",
            "features",
            "feature_blocks",
            "content_blocks",
            "footnotes",
        ),
        "supplier_offer": (
            "model_tokens",
            "indoor_model_tokens",
            "outdoor_model_tokens",
        ),
    }

    for table_name, column_names in required_columns.items():
        table = SQLModel.metadata.tables[table_name]
        for column_name in column_names:
            assert table.c[column_name].nullable is False


def test_extensible_workflow_enums_use_string_database_columns():
    for table_name, column_name in (
        ("customer", "type"),
        ("order", "target_currency"),
    ):
        column_type = SQLModel.metadata.tables[table_name].c[column_name].type
        assert isinstance(column_type, String)
        assert not isinstance(column_type, Enum)


def test_model_foreign_keys_match_database_delete_actions():
    expected_actions = {
        ("customer_branches", "customer_id"): "CASCADE",
        ("order", "customer_branch_id"): "SET NULL",
        ("product", "brand_id"): "SET NULL",
        ("product", "series_id"): "SET NULL",
        ("product_attachment", "product_id"): "CASCADE",
        ("product_image_variant", "product_image_id"): "CASCADE",
        ("product_main_image_cleanup_item", "batch_id"): "SET NULL",
        ("product_main_image_cleanup_item", "product_id"): "CASCADE",
        (
            "product_main_image_cleanup_item",
            "source_product_image_id",
        ): "SET NULL",
        ("product_series", "brand_id"): "SET NULL",
        ("service_estimate", "customer_id"): "SET NULL",
        ("service_estimate", "tariff_id"): "SET NULL",
        ("service_estimate_item", "estimate_id"): "CASCADE",
        ("service_estimate_item", "service_id"): "SET NULL",
        ("service_tariff_rule", "tariff_id"): "CASCADE",
        ("service_tariff_rule", "service_id"): "SET NULL",
        ("supplier_offer", "source_id"): "SET NULL",
    }

    for (table_name, column_name), expected_action in expected_actions.items():
        foreign_keys = list(
            SQLModel.metadata.tables[table_name].c[column_name].foreign_keys
        )
        assert len(foreign_keys) == 1
        assert foreign_keys[0].ondelete == expected_action


def test_model_indexes_match_current_database_shape():
    expected_unique_constraints = (
        (
            "import_media_cache",
            "source_url",
            "uq_import_media_cache_source_url",
            "ix_import_media_cache_source_url",
        ),
        (
            "staff_users",
            "legacy_installer_id",
            "uq_staff_users_legacy_installer_id",
            "ix_staff_users_legacy_installer_id",
        ),
    )

    for table_name, column_name, constraint_name, index_name in (
        expected_unique_constraints
    ):
        table = SQLModel.metadata.tables[table_name]
        assert any(
            isinstance(constraint, UniqueConstraint)
            and constraint.name == constraint_name
            and [column.name for column in constraint.columns] == [column_name]
            for constraint in table.constraints
        )
        assert any(
            index.name == index_name
            and not index.unique
            and [column.name for column in index.columns] == [column_name]
            for index in table.indexes
        )

    bank_receipt = SQLModel.metadata.tables["bank_receipt"]
    assert any(
        index.name == "ix_bank_receipt_account_balance_after"
        for index in bank_receipt.indexes
    )
