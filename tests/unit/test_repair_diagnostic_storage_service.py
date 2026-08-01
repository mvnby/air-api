import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import Order, OrderStatus
from services.general_media_storage_service import (
    LocalGeneralMediaStorage,
    S3CompatibleGeneralMediaStorage,
)
from services.repair_diagnostic_storage_service import (
    REPAIR_PUBLIC_WRITE_NAMESPACE,
    RepairDiagnosticStorageService,
)


@pytest.fixture
async def repair_storage_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'repair-storage.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session
    await engine.dispose()


def _namespace(*, nonce: str) -> str:
    return RepairDiagnosticStorageService.new_attempt_namespace(
        tenant_id=1,
        storefront_id=1,
        key_hash="a" * 64,
        nonce=nonce,
    )


def _referencing_order(path: str) -> Order:
    return Order(
        tenant_id=1,
        storefront_id=1,
        title="Repair with durable photo",
        status=OrderStatus.NEW_LEAD,
        workflow_type="repair",
        technical_meta={
            "repair": {
                "photos": {
                    "nameplate": [{"storage_path": path}],
                }
            }
        },
    )


@pytest.mark.asyncio
async def test_local_reconciler_deletes_crash_orphan_but_never_reference_or_current(
    repair_storage_session,
    tmp_path: Path,
):
    storage = LocalGeneralMediaStorage(base_dir=tmp_path / "media")
    referenced = await storage.save_media(
        content=b"referenced",
        namespace=_namespace(nonce="1" * 32),
        variant_type="nameplate-0",
        extension="jpg",
    )
    crash_orphan = await storage.save_media(
        content=b"crash-orphan",
        namespace=_namespace(nonce="2" * 32),
        variant_type="nameplate-0",
        extension="jpg",
    )
    current = await storage.save_media(
        content=b"current",
        namespace=_namespace(nonce="3" * 32),
        variant_type="nameplate-0",
        extension="jpg",
    )
    now = datetime.now(timezone.utc)
    old_timestamp = (now - timedelta(hours=25)).timestamp()
    for path in (referenced.path, crash_orphan.path):
        os.utime(path, (old_timestamp, old_timestamp))
    repair_storage_session.add(_referencing_order(referenced.path))
    await repair_storage_session.commit()

    deleted = await RepairDiagnosticStorageService.reconcile_orphans(
        repair_storage_session,
        storage=storage,
        now=now,
    )

    assert deleted == 1
    assert await storage.read_media(referenced.path) == b"referenced"
    with pytest.raises(FileNotFoundError):
        await storage.read_media(crash_orphan.path)
    assert await storage.read_media(current.path) == b"current"


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.deleted: list[str] = []

    def put_object(self, *, Key, Body, **_kwargs):
        self.objects[Key] = {
            "Body": bytes(Body),
            "LastModified": datetime.now(timezone.utc),
        }

    def list_objects_v2(self, *, Prefix, **_kwargs):
        return {
            "Contents": [
                {"Key": key, "LastModified": value["LastModified"]}
                for key, value in sorted(self.objects.items())
                if key.startswith(Prefix)
            ]
        }

    def delete_object(self, *, Key, **_kwargs):
        self.deleted.append(Key)
        self.objects.pop(Key, None)


@pytest.mark.asyncio
async def test_s3_reconciler_is_prefix_bounded_and_reference_safe(
    repair_storage_session,
):
    client = _FakeS3Client()
    storage = S3CompatibleGeneralMediaStorage(
        bucket="repair-media",
        endpoint_url="https://r2.example.test",
        public_base_url="https://media.example.test",
        key_prefix="shared-media",
        provider_name="r2",
        client=client,
    )
    referenced = await storage.save_media(
        content=b"referenced-r2",
        namespace=_namespace(nonce="4" * 32),
        variant_type="nameplate-0",
        extension="jpg",
    )
    crash_orphan = await storage.save_media(
        content=b"orphan-r2",
        namespace=_namespace(nonce="5" * 32),
        variant_type="nameplate-0",
        extension="jpg",
    )
    outside_key = "shared-media/unrelated/object.jpg"
    client.objects[outside_key] = {
        "Body": b"outside",
        "LastModified": datetime.now(timezone.utc) - timedelta(days=2),
    }
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    client.objects[referenced.path]["LastModified"] = old
    client.objects[crash_orphan.path]["LastModified"] = old
    repair_storage_session.add(_referencing_order(referenced.path))
    await repair_storage_session.commit()

    deleted = await RepairDiagnosticStorageService.reconcile_orphans(
        repair_storage_session,
        storage=storage,
        now=datetime.now(timezone.utc),
    )

    assert deleted == 1
    assert client.deleted == [crash_orphan.path]
    assert referenced.path in client.objects
    assert outside_key in client.objects
    assert f"/{REPAIR_PUBLIC_WRITE_NAMESPACE}/" in referenced.path
