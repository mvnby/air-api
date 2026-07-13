from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    CustomerEquipment,
    EquipmentOrderLink,
    EquipmentServiceEventType,
    EquipmentServiceHistory,
    EquipmentWarrantyCoverage,
    Order,
    OrderAttachmentLink,
    OrderWorkStage,
    ServiceAttachment,
)
from scripts.migrate_service_attachments import (
    MigrationStats,
    _is_existing_attachment,
    extract_order_candidates,
    extract_stage_candidates,
    migrate_equipment_links,
    migrate_legacy_coverages,
)


@pytest.fixture
async def migration_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'attachment-migration.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


def test_extract_order_candidates_deduplicates_and_prefers_equipment_context():
    order = Order(
        id=17,
        technical_meta={
            "telegram_attachments": [
                {
                    "file_id": "same-nameplate",
                    "filename": "plate.jpg",
                    "mime_type": "image/jpeg",
                    "purpose": "nameplate",
                    "attached_at": "2026-07-01T10:00:00Z",
                },
                {"filename": "missing-source.jpg", "mime_type": "image/jpeg"},
            ],
            "repair": {
                "nameplate_recognitions": [
                    {
                        "file_id": "same-nameplate",
                        "filename": "plate.jpg",
                        "mime_type": "image/jpeg",
                        "equipment_id": "81",
                        "component_id": "82",
                        "raw_text": "  Model   ABC  ",
                    }
                ]
            },
        },
    )

    candidates = extract_order_candidates(order)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.identity == (17, "same-nameplate", "nameplate")
    assert candidate.equipment_id == 81
    assert candidate.component_id == 82
    assert candidate.transcript == "Model ABC"
    assert candidate.captured_at is None


def test_extract_stage_candidates_parses_photos_and_documents_without_io():
    stage = OrderWorkStage(
        id=5,
        order_id=17,
        name="Commissioning",
        installer_report=(
            "Completed\n"
            "- Фото: telegram-photo-id\n"
            "- Документ: commissioning report.pdf (telegram-document-id)\n"
        ),
    )

    candidates = extract_stage_candidates(stage)

    assert [(item.file_id, item.category) for item in candidates] == [
        ("telegram-photo-id", "installation_result"),
        ("telegram-document-id", "document"),
    ]
    assert candidates[0].work_stage_id == 5
    assert candidates[1].filename == "commissioning report.pdf"
    assert candidates[1].mime_type == "application/pdf"


@pytest.mark.asyncio
async def test_migration_idempotency_helpers_detect_existing_rows(migration_session):
    order = Order(id=17, title="Legacy order")
    equipment = CustomerEquipment(
        id=81,
        customer_id=1,
        source_order_id=17,
        warranty_started_at=datetime(2026, 1, 1),
        warranty_expires_at=datetime(2028, 1, 1),
        warranty_terms="Legacy terms",
    )
    history = EquipmentServiceHistory(
        equipment_id=81,
        order_id=17,
        event_type=EquipmentServiceEventType.REPAIR,
    )
    attachment = ServiceAttachment(
        original_filename="plate.jpg",
        mime_type="image/jpeg",
        telegram_file_id="existing-file-id",
    )
    migration_session.add_all([order, equipment, history, attachment])
    await migration_session.flush()
    migration_session.add(
        OrderAttachmentLink(
            order_id=17,
            attachment_id=int(attachment.id),
            category="nameplate",
        )
    )
    await migration_session.commit()

    candidate = extract_order_candidates(
        Order(
            id=17,
            technical_meta={
                "telegram_attachments": [
                    {
                        "file_id": "existing-file-id",
                        "filename": "plate.jpg",
                        "mime_type": "image/jpeg",
                        "purpose": "nameplate",
                    }
                ]
            },
        )
    )[0]
    assert await _is_existing_attachment(migration_session, candidate)

    first = MigrationStats()
    await migrate_equipment_links(migration_session, execute=True, order_id=17, stats=first)
    await migrate_legacy_coverages(migration_session, execute=True, order_id=17, stats=first)
    await migration_session.commit()
    second = MigrationStats()
    await migrate_equipment_links(migration_session, execute=True, order_id=17, stats=second)
    await migrate_legacy_coverages(migration_session, execute=True, order_id=17, stats=second)

    assert first.equipment_links_created == 2
    assert first.legacy_coverages_created == 1
    assert second.equipment_links_created == 0
    assert second.legacy_coverages_created == 0
    links = list((await migration_session.execute(EquipmentOrderLink.__table__.select())).all())
    coverages = list((await migration_session.execute(EquipmentWarrantyCoverage.__table__.select())).all())
    assert {(row.equipment_id, row.order_id, row.role) for row in links} == {
        (81, 17, "sale"),
        (81, 17, "repair"),
    }
    assert len(coverages) == 1
    assert coverages[0].coverage_type == "legacy"
    assert coverages[0].starts_at == datetime(2026, 1, 1)
    assert coverages[0].policy_snapshot == {"migration": "customer_equipment_legacy_fields"}
