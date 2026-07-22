from sqlalchemy import CheckConstraint, Enum, String, UniqueConstraint
from sqlmodel import SQLModel

import models  # noqa: F401


def test_required_model_columns_match_database_nullability():
    required_columns = {
        "brand_feature": ("aliases",),
        "feature": ("aliases",),
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
        ("feature", "brand_id"): "SET NULL",
        ("feature_brand_link", "feature_id"): "CASCADE",
        ("feature_series_link", "feature_id"): "CASCADE",
        ("feature_product_link", "feature_id"): "CASCADE",
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

    lead = SQLModel.metadata.tables["lead"]
    assert any(
        index.name == "uq_lead_bot_source_fingerprint"
        and index.unique
        and [column.name for column in index.columns] == ["source_fingerprint"]
        and str(index.dialect_options["postgresql"]["where"])
        == "source = 'bot' AND source_fingerprint IS NOT NULL"
        for index in lead.indexes
    )

    recognition = SQLModel.metadata.tables["customer_requisites_recognition"]
    assert any(
        index.name == "uq_customer_requisites_telegram_message"
        and index.unique
        and [column.name for column in index.columns]
        == ["source", "telegram_user_id", "telegram_chat_id", "telegram_message_id"]
        for index in recognition.indexes
    )

    work_stage = SQLModel.metadata.tables["order_work_stage"]
    assert any(
        index.name == "uq_unassigned_order_work_stage_schedule"
        and index.unique
        and [column.name for column in index.columns] == ["order_id", "name", "start_time"]
        and str(index.dialect_options["postgresql"]["where"])
        == "installer_id IS NULL AND start_time IS NOT NULL"
        for index in work_stage.indexes
    )


def test_communication_foundation_metadata_has_durable_uniqueness_and_claim_indexes():
    outbox = SQLModel.metadata.tables["integration_outbox_event"]
    inbox = SQLModel.metadata.tables["consumer_inbox"]
    delivery = SQLModel.metadata.tables["communication_delivery"]
    runtime = SQLModel.metadata.tables["communication_runtime_state"]

    assert [column.name for column in runtime.primary_key.columns] == ["channel"]
    assert runtime.c.mode.nullable is False
    assert runtime.c.canary_run_id.nullable is True
    assert runtime.c.canary_run_id.type.length == 36
    assert runtime.c.control_revision.nullable is False
    assert runtime.c.status.nullable is False
    assert any(
        index.name == "ix_communication_runtime_state_heartbeat_at"
        and [column.name for column in index.columns] == ["heartbeat_at"]
        for index in runtime.indexes
    )
    for constraint_name in (
        "ck_communication_runtime_channel_nonempty",
        "ck_communication_runtime_mode_valid",
        "ck_communication_runtime_canary_scope_valid",
        "ck_communication_runtime_control_revision_non_negative",
        "ck_communication_runtime_status_valid",
    ):
        assert any(
            isinstance(constraint, CheckConstraint)
            and constraint.name == constraint_name
            for constraint in runtime.constraints
        )

    assert [column.name for column in inbox.primary_key.columns] == [
        "consumer_name",
        "event_id",
    ]
    assert outbox.c.idempotency_key.nullable is True
    assert outbox.c.deduplication_key.type.length == 255
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_integration_outbox_event_deduplication_key"
        and [column.name for column in constraint.columns] == ["deduplication_key"]
        for constraint in outbox.constraints
    )
    assert any(
        index.name == "ix_integration_outbox_event_claim"
        and [column.name for column in index.columns]
        == ["status", "available_at", "priority", "occurred_at"]
        for index in outbox.indexes
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name
        == "uq_communication_delivery_event_channel_recipient_template"
        and [column.name for column in constraint.columns]
        == ["event_id", "channel", "recipient_key", "template_version"]
        for constraint in delivery.constraints
    )
    assert any(
        index.name == "ix_communication_delivery_claim"
        and [column.name for column in index.columns]
        == ["status", "available_at", "priority", "created_at"]
        for index in delivery.indexes
    )
    assert any(
        index.name == "ix_communication_delivery_channel_claim"
        and [column.name for column in index.columns]
        == ["channel", "priority", "available_at", "created_at", "delivery_id"]
        and str(index.dialect_options["postgresql"]["where"])
        == "status IN ('queued', 'retry')"
        for index in delivery.indexes
    )
    assert any(
        index.name == "ix_communication_delivery_channel_recovery"
        and [column.name for column in index.columns]
        == ["channel", "lease_expires_at", "created_at", "delivery_id"]
        and str(index.dialect_options["postgresql"]["where"])
        == "status = 'running'"
        for index in delivery.indexes
    )
    assert any(
        isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_outbox_status_valid"
        for constraint in outbox.constraints
    )
    assert any(
        isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_delivery_status_valid"
        for constraint in delivery.constraints
    )
    for constraint_name in (
        "ck_delivery_active_attempts_remaining",
        "ck_delivery_attempt_phase",
        "ck_delivery_attempts_within_max",
        "ck_delivery_lease_state",
        "ck_delivery_provider_message_state",
        "ck_delivery_terminal_timestamps",
    ):
        assert any(
            isinstance(constraint, CheckConstraint)
            and constraint.name == constraint_name
            for constraint in delivery.constraints
        )
