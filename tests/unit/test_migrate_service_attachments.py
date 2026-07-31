from datetime import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    Customer,
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
from models.tenancy import TenantScope
from services.service_attachment_presenter import legacy_attachment_source_key
from services.private_attachment_storage_service import StoredPrivateObject
from scripts.migrate_service_attachments import (
    AttachmentDownloadError,
    LegacyAttachmentCandidate,
    MigrationStats,
    _telegram_file_url,
    _is_existing_attachment,
    _validate_legacy_source_url,
    download_candidate,
    extract_order_candidates,
    extract_stage_candidates,
    migrate_attachments,
    migrate_equipment_links,
    migrate_legacy_coverages,
)


TEST_TENANT_SCOPE = TenantScope(
    tenant_id=1,
    storefront_id=1,
    is_system=True,
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
        tenant_id=1,
        storefront_id=1,
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
    assert candidate.captured_at == datetime(2026, 7, 1, 10, 0)
    assert candidate.provenance == (
        "technical_meta.repair.nameplate_recognitions",
        "technical_meta.telegram_attachments",
    )


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


def test_candidate_identity_preserves_distinct_telegram_messages_and_work_stages():
    base = {
        "order_id": 17,
        "file_id": "same-file",
        "filename": "photo.jpg",
        "mime_type": "image/jpeg",
        "category": "installation_result",
        "source": "telegram_bot",
    }
    first_message = LegacyAttachmentCandidate(**base, telegram_chat_id=10, telegram_message_id=20)
    second_message = LegacyAttachmentCandidate(**base, telegram_chat_id=10, telegram_message_id=21)
    first_stage = LegacyAttachmentCandidate(**base, work_stage_id=1)
    second_stage = LegacyAttachmentCandidate(**base, work_stage_id=2)

    assert first_message.identity != second_message.identity
    assert first_stage.identity != second_stage.identity


@pytest.mark.asyncio
async def test_telegram_download_error_never_exposes_bot_token(monkeypatch):
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.BOT_TOKEN", "secret-bot-token")
    transport = httpx.MockTransport(lambda request: httpx.Response(401, request=request))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(AttachmentDownloadError) as error:
            await _telegram_file_url(client, "file-id")

    assert error.value.configuration is True
    assert "secret-bot-token" not in str(error.value)
    assert "HTTP 401" in str(error.value)


def test_legacy_url_validation_rejects_arbitrary_and_private_hosts(monkeypatch):
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.PUBLIC_SITE_URL", "https://mvn.by")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.MEDIA_S3_PUBLIC_BASE_URL", "")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.PRODUCT_MEDIA_S3_PUBLIC_BASE_URL", "")

    assert _validate_legacy_source_url("/media/order/photo.jpg") == "https://mvn.by/media/order/photo.jpg"
    with pytest.raises(AttachmentDownloadError, match="not allowlisted"):
        _validate_legacy_source_url("https://example.org/private.jpg")
    with pytest.raises(AttachmentDownloadError, match="non-public"):
        _validate_legacy_source_url("https://127.0.0.1/private.jpg")
    with pytest.raises(AttachmentDownloadError, match="HTTPS"):
        _validate_legacy_source_url("http://mvn.by/private.jpg")


@pytest.mark.asyncio
async def test_download_falls_back_from_legacy_url_to_telegram(monkeypatch):
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.PUBLIC_SITE_URL", "https://mvn.by")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.MEDIA_S3_PUBLIC_BASE_URL", "")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.PRODUCT_MEDIA_S3_PUBLIC_BASE_URL", "")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.BOT_TOKEN", "123:test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "mvn.by":
            return httpx.Response(404, request=request)
        if request.url.path.endswith("/getFile"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"file_path": "photos/file.jpg"}},
                request=request,
            )
        return httpx.Response(200, content=b"telegram-content", request=request)

    candidate = LegacyAttachmentCandidate(
        order_id=17,
        file_id="telegram-file-id",
        url="https://mvn.by/missing.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        category="other",
        source="legacy",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await download_candidate(client, candidate) == b"telegram-content"


@pytest.mark.asyncio
async def test_download_rejects_legacy_integrity_mismatch(monkeypatch):
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.PUBLIC_SITE_URL", "https://mvn.by")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.MEDIA_S3_PUBLIC_BASE_URL", "")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.PRODUCT_MEDIA_S3_PUBLIC_BASE_URL", "")
    candidate = LegacyAttachmentCandidate(
        order_id=17,
        file_id=None,
        url="https://mvn.by/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        category="other",
        source="legacy",
        expected_content_hash="0" * 64,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"different", request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(AttachmentDownloadError, match="SHA-256"):
            await download_candidate(client, candidate)


@pytest.mark.asyncio
async def test_download_rejects_legacy_size_mismatch(monkeypatch):
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.PUBLIC_SITE_URL", "https://mvn.by")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.MEDIA_S3_PUBLIC_BASE_URL", "")
    monkeypatch.setattr("scripts.migrate_service_attachments.settings.PRODUCT_MEDIA_S3_PUBLIC_BASE_URL", "")
    candidate = LegacyAttachmentCandidate(
        order_id=17,
        file_id=None,
        url="https://mvn.by/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        category="other",
        source="legacy",
        expected_size_bytes=99,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"short", request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(AttachmentDownloadError, match="size"):
            await download_candidate(client, candidate)


@pytest.mark.asyncio
async def test_private_copy_rejects_corrupt_storage_readback(migration_session, monkeypatch):
    class CorruptReadbackStorage:
        provider_name = "test-private"

        async def save(self, *, content, content_hash, extension, content_type, variant):
            return StoredPrivateObject(
                provider=self.provider_name,
                storage_key=f"private/{content_hash}/{variant}.{extension}",
                content_hash=content_hash,
                size_bytes=len(content),
            )

        async def read(self, storage_key):
            return b"corrupt-readback"

        async def exists(self, storage_key):
            return False

        async def delete(self, storage_key):
            return None

        async def verify_writable(self):
            return None

        async def presign(self, storage_key, *, expires_seconds, download_name=None):
            return None

    customer = Customer(tenant_id=1, id=1, name="Legacy customer", phone="+375290000001")
    order = Order(
        tenant_id=1,
        storefront_id=1,
        id=17,
        title="Legacy order",
        customer_id=1,
        technical_meta={
            "telegram_attachments": [
                {
                    "file_id": "private-copy-file",
                    "filename": "evidence.txt",
                    "mime_type": "text/plain",
                    "purpose": "document",
                }
            ]
        },
    )
    migration_session.add_all([customer, order])
    await migration_session.commit()
    monkeypatch.setattr(
        "scripts.service_attachment_migration.attachment_copy.download_candidate",
        lambda client, candidate: _async_value(b"verified-source"),
    )

    stats = MigrationStats()
    await migrate_attachments(
        migration_session,
        execute=True,
        order_id=17,
        stats=stats,
        storage=CorruptReadbackStorage(),
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert stats.attachments_verified == 1
    assert stats.attachments_storage_verified == 0
    assert stats.attachments_migrated == 0
    assert stats.attachments_unavailable == 1
    assert any("read-back integrity" in issue for issue in stats.issues)


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_execute_uses_advisory_lock_and_fails_closed_on_partial_result(monkeypatch):
    from scripts.service_attachment_migration import orchestrator

    required_tables = {
        "service_attachment",
        "order_attachment_link",
        "equipment_attachment_link",
        "equipment_order_link",
        "equipment_warranty_coverage",
    }

    class FakeConnection:
        async def run_sync(self, callback):
            return required_tables

    class ConnectionContext:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeEngine:
        def connect(self):
            return ConnectionContext()

    class FakeSession:
        def __init__(self):
            self.statements = []
            self.rolled_back = False
            self.committed = False

        def get_bind(self):
            return type("Bind", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()})()

        async def execute(self, statement, params=None):
            self.statements.append((statement, params))

        async def rollback(self):
            self.rolled_back = True

        async def commit(self):
            self.committed = True

    fake_session = FakeSession()

    class SessionContext:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeStorage:
        async def verify_writable(self):
            return None

    async def partial_attachment_migration(session, *, stats, **kwargs):
        stats.attachments_unavailable = 1

    async def no_op_migration(session, **kwargs):
        return None

    async def resolve_tenant_scope(session):
        return TEST_TENANT_SCOPE

    monkeypatch.setattr(orchestrator, "engine", FakeEngine())
    monkeypatch.setattr(orchestrator, "async_session_maker", lambda: SessionContext())
    monkeypatch.setattr(orchestrator, "get_private_attachment_storage", lambda: FakeStorage())
    monkeypatch.setattr(
        orchestrator.SystemTenantScopeResolver,
        "resolve",
        resolve_tenant_scope,
    )
    monkeypatch.setattr(orchestrator, "migrate_attachments", partial_attachment_migration)
    monkeypatch.setattr(orchestrator, "migrate_equipment_links", no_op_migration)
    monkeypatch.setattr(orchestrator, "migrate_legacy_coverages", no_op_migration)

    with pytest.raises(RuntimeError, match="rolled back"):
        await orchestrator.run(execute=True, order_id=None, allow_partial=False)

    assert fake_session.rolled_back is True
    assert fake_session.committed is False
    assert any("pg_advisory_xact_lock" in str(statement) for statement, _ in fake_session.statements)


@pytest.mark.asyncio
async def test_migration_idempotency_helpers_detect_existing_rows(migration_session):
    customer = Customer(tenant_id=1, id=1, name="Legacy customer", phone="+375290000001")
    order = Order(tenant_id=1, storefront_id=1, id=17, title="Legacy order", customer_id=1)
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
    migration_session.add_all([customer, order, equipment, history, attachment])
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
            tenant_id=1,
            storefront_id=1,
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


@pytest.mark.asyncio
async def test_url_only_candidate_is_idempotent_by_stable_source_key(migration_session):
    customer = Customer(tenant_id=1, id=1, name="Legacy customer", phone="+375290000001")
    order = Order(tenant_id=1, storefront_id=1, id=17, title="Legacy order", customer_id=1)
    candidate = LegacyAttachmentCandidate(
        order_id=17,
        file_id=None,
        url="https://mvn.by/media/legacy/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        category="installation_result",
        source="legacy",
    )
    attachment = ServiceAttachment(
        original_filename="photo.jpg",
        mime_type="image/jpeg",
        source_meta={"legacy_source_key": candidate.legacy_source_key},
    )
    migration_session.add_all([customer, order, attachment])
    await migration_session.flush()
    migration_session.add(
        OrderAttachmentLink(
            order_id=17,
            attachment_id=int(attachment.id),
            category="installation_result",
        )
    )
    await migration_session.commit()

    assert candidate.legacy_source_key == legacy_attachment_source_key(
        17,
        {
            "url": "https://mvn.by/media/legacy/photo.jpg",
            "filename": "photo.jpg",
            "purpose": "installation_result",
        },
    )
    assert await _is_existing_attachment(migration_session, candidate)


@pytest.mark.asyncio
async def test_migration_skips_cross_customer_equipment_order_links(migration_session):
    first_customer = Customer(tenant_id=1, id=1, name="First", phone="+375290000001")
    second_customer = Customer(tenant_id=1, id=2, name="Second", phone="+375290000002")
    foreign_order = Order(tenant_id=1, storefront_id=1, id=17, title="Foreign order", customer_id=2)
    equipment = CustomerEquipment(id=81, customer_id=1, source_order_id=17)
    migration_session.add_all([first_customer, second_customer, foreign_order, equipment])
    await migration_session.commit()

    stats = MigrationStats()
    await migrate_equipment_links(migration_session, execute=True, order_id=17, stats=stats)
    await migration_session.commit()

    assert stats.equipment_links_created == 0
    assert stats.equipment_link_conflicts == 1
    assert any("does not match equipment customer" in issue for issue in stats.issues)
    links = list((await migration_session.execute(EquipmentOrderLink.__table__.select())).all())
    assert links == []
