from pathlib import Path
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    Customer,
    CustomerEquipment,
    EquipmentComponent,
    Order,
    OrderInstaller,
    OrderProductLink,
    OrderStatus,
    OrderWorkStage,
    Product,
    StaffUser,
)
from services.bot_order_attachment_service import BotOrderAttachmentService
from services.bot_defect_act_service import BotDefectActService
from services.bot_repair_nameplate_service import BotRepairNameplateService
from services.bot_warranty_nameplate_service import BotWarrantyNameplateService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
from services.defect_act_ai_service import DefectActAIService
from services.general_media_storage_service import StoredGeneralMediaObject


class FakeGeneralMediaStorage:
    provider_name = "r2"

    async def save_media(self, **kwargs):
        return StoredGeneralMediaObject(
            url="https://cdn.mvn.by/media/orders/42/telegram/photo/hash.jpg",
            content_hash="b" * 64,
            storage_provider="r2",
            path="orders/42/telegram/photo/hash.jpg",
            size_bytes=len(kwargs["content"]),
        )


@pytest.fixture
async def sqlite_repair_nameplate_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bot_repair_nameplate.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_nameplate_normalization_cleans_repair_fields():
    extracted, flags = BotRepairNameplateService.normalize_extracted(
        {
            "brand": " Alaska ",
            "model": " ALASKA AL-12LHJ ",
            "serial_number": " SN 001 ",
            "capacity_btu": "12000 BTU/h",
            "refrigerant": " R-22 ",
            "refrigerant_charge": "R22/0.600kg",
            "confidence": "0.72",
        },
        "MODEL ALASKA AL-12LHJ\nRefrigerant/Charge R22/0.600kg",
    )

    assert extracted["equipment_brand"] == "Alaska"
    assert extracted["equipment_model"] == "ALASKA AL-12LHJ"
    assert extracted["equipment_serial_number"] == "SN 001"
    assert extracted["equipment_power"] == "12000 BTU/h"
    assert extracted["refrigerant_type"] == "R22"
    assert extracted["refrigerant_amount"] == "0,600 кг"
    assert flags["confidence"] == 0.72
    assert flags["is_valid"] is True


def test_nameplate_normalization_prefers_tcl_barcode_serial_candidate():
    extracted, flags = BotRepairNameplateService.normalize_extracted(
        {
            "brand": "TCL",
            "model": "TAC-12CHSD/UG11V3AH",
            "serial_number": "MO250310695980",
            "serial_candidates": [
                "MO250310695980",
                "2503106959",
                "140202APZ5W16254N000085",
            ],
            "confidence": 0.83,
        },
        "TAC-12CHSD/UG11V3AH\nMO250310695980\n2503106959\n140202APZ5W16254N000085",
    )

    assert extracted["equipment_model"] == "TAC-12CHSD/UG11V3AH"
    assert extracted["equipment_serial_number"] == "140202APZ5W16254N000085"
    assert flags["serial_candidates"][0] == "140202APZ5W16254N000085"
    assert "MO250310695980" in flags["serial_candidates"]
    assert "2503106959" in flags["serial_candidates"]
    assert "несколько похожих номеров" in flags["warnings"]["serial_candidates"]


def test_nameplate_normalization_decodes_tcl_factory_serial_details():
    extracted, flags = BotRepairNameplateService.normalize_extracted(
        {
            "brand": "TCL",
            "model": "TAC-09CHS/E",
            "serial_number": "11175WFC44ZG12500060",
        },
        "TAC-09CHS/E\n11175WFC44ZG12500060",
    )

    assert extracted["equipment_serial_number"] == "11175WFC44ZG12500060"
    assert flags["serial_details"] == {
        "format": "tcl_factory_20",
        "manufacturer_code": "1",
        "model_code": "1175",
        "unit_type_code": "W",
        "unit_type_label": "наружный блок",
        "order_date_code": "FC",
        "order_year": 2015,
        "order_month": 12,
        "batch_code": "44",
        "product_mark_code": "Z",
        "product_mark_label": "собранный блок",
        "production_date_code": "G125",
        "production_date": "2016-01-25",
        "product_serial_number": "00060",
    }


@pytest.mark.asyncio
async def test_nameplate_recognize_rejects_too_large_file_before_ocr(monkeypatch):
    async def fail_extract(*args, **kwargs):
        raise AssertionError("OCR should not run for oversized files")

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_ocr_text", fail_extract)

    with pytest.raises(ValueError, match="Файл слишком большой"):
        await BotRepairNameplateService.recognize_bytes(
            content=b"x" * (CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES + 1),
            filename="nameplate.jpg",
            mime_type="image/jpeg",
        )


@pytest.mark.asyncio
async def test_lists_active_repair_orders_for_manager(sqlite_repair_nameplate_session):
    repair_new = Order(title="Новый ремонт", status=OrderStatus.NEW_LEAD, workflow_type="repair")
    repair_execution = Order(title="Ремонт в работе", status=OrderStatus.EXECUTION, workflow_type="repair")
    repair_negotiation = Order(title="Ремонт в переговорах", status=OrderStatus.NEGOTIATION, workflow_type="repair")
    repair_closed = Order(title="Закрытый ремонт", status=OrderStatus.CLOSED, workflow_type="repair")
    install_execution = Order(title="Монтаж", status=OrderStatus.EXECUTION, workflow_type="sales_installation")
    sqlite_repair_nameplate_session.add(repair_new)
    sqlite_repair_nameplate_session.add(repair_execution)
    sqlite_repair_nameplate_session.add(repair_negotiation)
    sqlite_repair_nameplate_session.add(repair_closed)
    sqlite_repair_nameplate_session.add(install_execution)
    await sqlite_repair_nameplate_session.commit()

    orders = await BotRepairNameplateService.list_repair_orders(
        sqlite_repair_nameplate_session,
        telegram_user_id=777,
        can_attach_any=True,
    )

    assert {item["id"] for item in orders} == {
        repair_new.id,
        repair_execution.id,
        repair_negotiation.id,
    }


@pytest.mark.asyncio
async def test_executor_sees_only_assigned_repair_orders(sqlite_repair_nameplate_session):
    staff = StaffUser(
        display_name="Монтажник",
        status="active",
        primary_role="installer",
        roles=["installer"],
        telegram_id=777,
        legacy_installer_id=10,
    )
    assigned = Order(title="Назначенный ремонт", status=OrderStatus.EXECUTION, workflow_type="repair")
    legacy_assigned = Order(title="Старый ремонт", status=OrderStatus.EXECUTION, workflow_type="repair")
    other = Order(title="Чужой ремонт", status=OrderStatus.EXECUTION, workflow_type="repair")
    sqlite_repair_nameplate_session.add(staff)
    sqlite_repair_nameplate_session.add(assigned)
    sqlite_repair_nameplate_session.add(legacy_assigned)
    sqlite_repair_nameplate_session.add(other)
    await sqlite_repair_nameplate_session.flush()
    sqlite_repair_nameplate_session.add(OrderWorkStage(order_id=assigned.id, installer_id=10, name="Диагностика"))
    sqlite_repair_nameplate_session.add(OrderInstaller(order_id=legacy_assigned.id, installer_id=10))
    await sqlite_repair_nameplate_session.commit()

    orders = await BotRepairNameplateService.list_repair_orders(
        sqlite_repair_nameplate_session,
        telegram_user_id=777,
        can_attach_any=False,
    )

    assert {item["id"] for item in orders} == {assigned.id, legacy_assigned.id}


@pytest.mark.asyncio
async def test_apply_to_order_merges_without_overwriting_existing_repair_meta(sqlite_repair_nameplate_session):
    customer = Customer(name="Иван", phone="+375291234567")
    order = Order(
        customer=customer,
        title="Ремонт",
        status=OrderStatus.EXECUTION,
        workflow_type="repair",
        technical_meta={
            "repair": {
                "repair_status": "scheduled",
                "equipment_model": "Введено вручную",
                "customer_complaint": "Не охлаждает",
            }
        },
    )
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    result = await BotRepairNameplateService.apply_to_order(
        sqlite_repair_nameplate_session,
        int(order.id),
        extracted={
            "equipment_model": "ALASKA AL-12LHJ",
            "equipment_serial_number": "SN-001",
            "refrigerant_type": "R22",
            "refrigerant_amount": "0,600 кг",
        },
        raw_text="MODEL ALASKA AL-12LHJ",
        validation_flags={"warnings": {}, "is_valid": True},
        file_id="photo-file",
        filename="nameplate.jpg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
        can_attach_any=True,
    )

    assert result is not None
    assert result["applied"] == {
        "equipment_serial_number": "SN-001",
        "refrigerant_type": "R22",
        "refrigerant_amount": "0,600 кг",
    }
    assert result["conflicts"]["equipment_model"] == {
        "existing": "Введено вручную",
        "candidate": "ALASKA AL-12LHJ",
    }

    await sqlite_repair_nameplate_session.refresh(order)
    repair_meta = order.technical_meta["repair"]
    assert repair_meta["equipment_model"] == "Введено вручную"
    assert repair_meta["equipment_models"] == ["Введено вручную", "ALASKA AL-12LHJ"]
    assert repair_meta["equipment_serial_number"] == "SN-001"
    assert repair_meta["customer_complaint"] == "Не охлаждает"
    assert repair_meta["repair_status"] == "scheduled"
    assert repair_meta["nameplate_recognitions"][0]["purpose"] == "repair_nameplate"
    assert order.technical_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY][0]["purpose"] == "repair_nameplate"


@pytest.mark.asyncio
async def test_apply_to_order_stores_repair_nameplate_content(
    sqlite_repair_nameplate_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "services.bot_order_attachment_service.get_general_media_storage",
        lambda: FakeGeneralMediaStorage(),
    )
    order = Order(id=42, title="Ремонт", status=OrderStatus.EXECUTION, workflow_type="repair")
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    result = await BotRepairNameplateService.apply_to_order(
        sqlite_repair_nameplate_session,
        int(order.id),
        extracted={"equipment_serial_number": "SN-001"},
        raw_text="SERIAL SN-001",
        validation_flags={"warnings": {}, "is_valid": True},
        file_id="photo-file",
        filename="nameplate.jpeg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
        can_attach_any=True,
        file_content=b"nameplate-content",
    )

    assert result is not None
    await sqlite_repair_nameplate_session.refresh(order)
    attachment = order.technical_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY][0]
    assert attachment["url"] == "https://cdn.mvn.by/media/orders/42/telegram/photo/hash.jpg"
    assert attachment["storage_provider"] == "r2"
    assert attachment["content_hash"] == "b" * 64
    assert attachment["size_bytes"] == len(b"nameplate-content")


@pytest.mark.asyncio
async def test_apply_to_order_preserves_new_attachment_when_order_already_has_telegram_attachment(
    sqlite_repair_nameplate_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "services.bot_order_attachment_service.get_general_media_storage",
        lambda: FakeGeneralMediaStorage(),
    )
    order = Order(
        id=42,
        title="Ремонт",
        status=OrderStatus.EXECUTION,
        workflow_type="repair",
        technical_meta={
            BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY: [
                {
                    "source": "telegram_bot",
                    "file_id": "old-photo",
                    "filename": "old.jpg",
                    "mime_type": "image/jpeg",
                    "kind": "photo",
                    "purpose": "repair_nameplate",
                    "attached_at": "2026-07-02T13:39:43",
                }
            ],
            "repair": {"repair_status": "scheduled"},
        },
    )
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    result = await BotRepairNameplateService.apply_to_order(
        sqlite_repair_nameplate_session,
        int(order.id),
        extracted={"equipment_serial_number": "SN-002"},
        raw_text="SERIAL SN-002",
        validation_flags={"warnings": {}, "is_valid": True},
        file_id="new-photo",
        filename="nameplate.jpeg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=56,
        can_attach_any=True,
        file_content=b"second-nameplate-content",
    )

    assert result is not None
    await sqlite_repair_nameplate_session.refresh(order)
    attachments = order.technical_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY]
    assert [attachment["file_id"] for attachment in attachments] == ["old-photo", "new-photo"]
    assert attachments[1]["url"] == "https://cdn.mvn.by/media/orders/42/telegram/photo/hash.jpg"
    assert attachments[1]["storage_provider"] == "r2"
    assert order.technical_meta["repair"]["repair_status"] == "scheduled"
    assert order.technical_meta["repair"]["nameplate_recognitions"][0]["content_hash"] == "b" * 64


@pytest.mark.asyncio
async def test_apply_to_order_updates_existing_repair_nameplate_attachment_url(
    sqlite_repair_nameplate_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "services.bot_order_attachment_service.get_general_media_storage",
        lambda: FakeGeneralMediaStorage(),
    )
    order = Order(
        id=42,
        title="Ремонт",
        status=OrderStatus.EXECUTION,
        workflow_type="repair",
        technical_meta={
            BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY: [
                {
                    "source": "telegram_bot",
                    "file_id": "photo-file",
                    "filename": "nameplate.jpg",
                    "mime_type": "image/jpeg",
                    "kind": "photo",
                    "purpose": "repair_nameplate",
                    "attached_at": "2026-07-02T13:39:43",
                }
            ],
            "repair": {"repair_status": "scheduled"},
        },
    )
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    result = await BotRepairNameplateService.apply_to_order(
        sqlite_repair_nameplate_session,
        int(order.id),
        extracted={"equipment_serial_number": "SN-003"},
        raw_text="SERIAL SN-003",
        validation_flags={"warnings": {}, "is_valid": True},
        file_id="photo-file",
        filename="nameplate.jpeg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=56,
        can_attach_any=True,
        file_content=b"updated-nameplate-content",
    )

    assert result is not None
    await sqlite_repair_nameplate_session.refresh(order)
    attachments = order.technical_meta[BotOrderAttachmentService.TELEGRAM_ATTACHMENTS_META_KEY]
    assert len(attachments) == 1
    assert attachments[0]["file_id"] == "photo-file"
    assert attachments[0]["url"] == "https://cdn.mvn.by/media/orders/42/telegram/photo/hash.jpg"
    assert attachments[0]["storage_provider"] == "r2"
    assert attachments[0]["content_hash"] == "b" * 64
    repair_attachment = order.technical_meta["repair"]["nameplate_recognitions"][0]
    assert repair_attachment["url"] == "https://cdn.mvn.by/media/orders/42/telegram/photo/hash.jpg"


@pytest.mark.asyncio
async def test_apply_to_order_accepts_negotiation_repair_order(sqlite_repair_nameplate_session):
    order = Order(title="Ремонт", status=OrderStatus.NEGOTIATION, workflow_type="repair")
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    result = await BotRepairNameplateService.apply_to_order(
        sqlite_repair_nameplate_session,
        int(order.id),
        extracted={"equipment_serial_number": "SN-121"},
        raw_text="SN-121",
        validation_flags={},
        file_id="photo-file",
        filename="nameplate.jpg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
        can_attach_any=True,
    )

    assert result is not None
    await sqlite_repair_nameplate_session.refresh(order)
    assert order.technical_meta["repair"]["equipment_serial_number"] == "SN-121"


@pytest.mark.asyncio
async def test_apply_to_order_rejects_non_repair_order(sqlite_repair_nameplate_session):
    order = Order(title="Монтаж", status=OrderStatus.EXECUTION, workflow_type="sales_installation")
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    result = await BotRepairNameplateService.apply_to_order(
        sqlite_repair_nameplate_session,
        int(order.id),
        extracted={"equipment_model": "ALASKA"},
        raw_text="MODEL ALASKA",
        validation_flags={},
        file_id="photo-file",
        filename="nameplate.jpg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
        can_attach_any=True,
    )

    assert result is None


@pytest.mark.asyncio
async def test_build_diagnostic_comment_draft_uses_ai_and_previews_changes(sqlite_repair_nameplate_session, monkeypatch):
    order = Order(
        title="Ремонт",
        status=OrderStatus.EXECUTION,
        workflow_type="repair",
        technical_meta={
            "repair": {
                "equipment_model": "ALASKA AL-12LHJ",
                "diagnostic_result": "Старая диагностика",
            }
        },
    )
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    async def fake_generate(payload):
        assert payload.equipment_model == "ALASKA AL-12LHJ"
        assert "компрессор" in payload.extra_context
        return {
            "diagnostic_result": "Компрессор не создает давление в контуре.",
            "compressor_check_result": "Напряжение 220 В присутствует, рабочий ток компрессора отсутствует.",
            "repair_recommendation": "Рекомендована замена компрессора или оборудования.",
        }

    monkeypatch.setattr(DefectActAIService, "generate_repair_meta", fake_generate)

    draft = await BotDefectActService.build_diagnostic_comment_draft(
        sqlite_repair_nameplate_session,
        order_id=int(order.id),
        comment="подключили шланги, утечку устранили, компрессор не качает",
    )

    assert draft is not None
    changes = draft["merge_preview"]["changes"]
    assert changes["diagnostic_result"]["existing"] == "Старая диагностика"
    assert changes["diagnostic_result"]["candidate"] == "Компрессор не создает давление в контуре."
    assert changes["compressor_check_result"]["candidate"].startswith("Напряжение 220 В")


@pytest.mark.asyncio
async def test_build_diagnostic_preset_draft_is_deterministic_and_compact(sqlite_repair_nameplate_session):
    order = Order(
        title="Ремонт",
        status=OrderStatus.EXECUTION,
        workflow_type="repair",
        technical_meta={"repair": {"equipment_brand": "MDV", "equipment_model": "MDSAF-12HRN1"}},
    )
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    draft = await BotDefectActService.build_diagnostic_preset_draft(
        sqlite_repair_nameplate_session,
        order_id=int(order.id),
        fault_type="compressor_short_circuit",
    )

    assert draft is not None
    repair_meta = draft["repair_meta"]
    assert repair_meta["fault_type"] == "compressor_short_circuit"
    assert repair_meta["decision"] == "write_off"
    assert repair_meta["repair_possible"] == "Нет"
    assert "измерение сопротивления обмоток" in repair_meta["inspection_work_done"]
    assert "подлежит выводу из эксплуатации и списанию" in repair_meta["technical_conclusion"]
    assert isinstance(repair_meta["structured_diagnosis"], dict)
    assert draft["merge_preview"]["changes"]["structured_diagnosis"]["candidate"]["repairable"] is False


def test_preview_comment_merge_keeps_structured_values_typed():
    preview = BotDefectActService.preview_comment_merge(
        {"hidden_defects_possible": True},
        {
            "hidden_defects_possible": False,
            "inspection_codes": ["visual_inspection", "winding_resistance_test"],
            "structured_diagnosis": {"fault_type": "compressor_short_circuit", "repairable": False},
        },
    )

    assert preview["changes"]["hidden_defects_possible"]["candidate"] is False
    assert preview["changes"]["inspection_codes"]["candidate"] == [
        "visual_inspection",
        "winding_resistance_test",
    ]
    assert preview["changes"]["structured_diagnosis"]["candidate"]["repairable"] is False


@pytest.mark.asyncio
async def test_apply_diagnostic_comment_updates_repair_meta_and_keeps_history(sqlite_repair_nameplate_session):
    order = Order(title="Ремонт", status=OrderStatus.EXECUTION, workflow_type="repair")
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    result = await BotDefectActService.apply_diagnostic_comment(
        sqlite_repair_nameplate_session,
        int(order.id),
        repair_meta_draft={
            "diagnostic_result": "Выявлен отказ компрессора.",
            "repair_recommendation": "Рекомендована замена компрессора.",
        },
        raw_comment="компрессор не качает",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
        can_attach_any=True,
    )

    assert result is not None
    assert set(result["changes"]) == {"diagnostic_result", "repair_recommendation"}
    await sqlite_repair_nameplate_session.refresh(order)
    repair_meta = order.technical_meta["repair"]
    assert repair_meta["diagnostic_result"] == "Выявлен отказ компрессора."
    assert repair_meta["repair_recommendation"] == "Рекомендована замена компрессора."
    assert repair_meta["bot_diagnostic_comments"][0]["comment"] == "компрессор не качает"
    assert repair_meta["bot_diagnostic_comments"][0]["applied_fields"] == [
        "diagnostic_result",
        "repair_recommendation",
    ]


@pytest.mark.asyncio
async def test_warranty_nameplate_lists_today_installations_first(sqlite_repair_nameplate_session):
    today_order = Order(
        title="Сегодняшний монтаж",
        status=OrderStatus.EXECUTION,
        workflow_type="sales_installation",
        installation_date=datetime(2026, 6, 18, 14, 0, 0),
    )
    other_execution = Order(
        title="Другой монтаж",
        status=OrderStatus.EXECUTION,
        workflow_type="sales_installation",
        installation_date=datetime(2026, 6, 17, 14, 0, 0),
    )
    repair = Order(title="Ремонт", status=OrderStatus.EXECUTION, workflow_type="repair")
    sqlite_repair_nameplate_session.add(today_order)
    sqlite_repair_nameplate_session.add(other_execution)
    sqlite_repair_nameplate_session.add(repair)
    await sqlite_repair_nameplate_session.commit()

    result = await BotWarrantyNameplateService.list_installation_orders(
        sqlite_repair_nameplate_session,
        telegram_user_id=777,
        can_attach_any=True,
        now=datetime(2026, 6, 18, 10, 0, 0),
    )

    assert result["scope"] == "today"
    assert [item["id"] for item in result["items"]] == [today_order.id]


@pytest.mark.asyncio
async def test_warranty_nameplate_falls_back_to_execution_installations(sqlite_repair_nameplate_session):
    order = Order(
        title="Монтаж без даты сегодня",
        status=OrderStatus.EXECUTION,
        workflow_type="service_work",
        installation_date=datetime(2026, 6, 17, 14, 0, 0),
    )
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.commit()

    result = await BotWarrantyNameplateService.list_installation_orders(
        sqlite_repair_nameplate_session,
        telegram_user_id=777,
        can_attach_any=True,
        now=datetime(2026, 6, 18, 10, 0, 0),
    )

    assert result["scope"] == "execution"
    assert [item["id"] for item in result["items"]] == [order.id]


@pytest.mark.asyncio
async def test_warranty_nameplate_creates_order_equipment_and_updates_selected_component(sqlite_repair_nameplate_session):
    customer = Customer(name="Иван", phone="+375291234567")
    product = Product(
        title="Haier Flexis 12",
        slug="haier-flexis-12",
        price=2000,
        specs={
            "indoor_model": "AS25S2SF1FA",
            "outdoor_model": "1U25S2SM1FA",
            "refrigerant": "R32",
        },
    )
    sqlite_repair_nameplate_session.add(customer)
    sqlite_repair_nameplate_session.add(product)
    await sqlite_repair_nameplate_session.flush()
    order = Order(
        customer_id=customer.id,
        title="Продажа и монтаж",
        status=OrderStatus.EXECUTION,
        workflow_type="sales_installation",
        installation_date=datetime(2026, 6, 18, 14, 0, 0),
    )
    sqlite_repair_nameplate_session.add(order)
    await sqlite_repair_nameplate_session.flush()
    sqlite_repair_nameplate_session.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1))
    await sqlite_repair_nameplate_session.commit()

    result = await BotWarrantyNameplateService.apply_to_order(
        sqlite_repair_nameplate_session,
        int(order.id),
        unit_type="indoor_unit",
        extracted={
            "equipment_brand": "Haier",
            "equipment_model": "AS25S2SF1FA",
            "equipment_serial_number": "SN-IN-001",
            "refrigerant_type": "R32",
        },
        raw_text="MODEL AS25S2SF1FA SERIAL SN-IN-001",
        validation_flags={"warnings": {}, "is_valid": True},
        file_id="photo-file",
        filename="nameplate.jpg",
        mime_type="image/jpeg",
        telegram_user_id=777,
        telegram_chat_id=100,
        telegram_message_id=55,
        can_attach_any=True,
    )

    assert result is not None
    assert result["component"]["applied"]["serial"] == "SN-IN-001"
    equipment = await sqlite_repair_nameplate_session.get(CustomerEquipment, result["equipment_id"])
    component = await sqlite_repair_nameplate_session.get(EquipmentComponent, result["component_id"])
    await sqlite_repair_nameplate_session.refresh(order)

    assert equipment is not None
    assert equipment.source_order_id == order.id
    assert equipment.warranty_started_at == datetime(2026, 6, 18, 14, 0, 0)
    assert equipment.warranty_expires_at.year == 2028
    assert component is not None
    assert component.component_type == "indoor_unit"
    assert component.model == "AS25S2SF1FA"
    assert component.serial == "SN-IN-001"
    assert order.technical_meta["warranty_nameplate_recognitions"][0]["purpose"] == "warranty_nameplate"
