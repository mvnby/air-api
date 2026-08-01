import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import (
    Lead,
    Order,
    Product,
    PublicWriteIdempotency,
    ServiceAttachment,
    Storefront,
)
from schemas import (
    OrderPayload,
    ProductAvailabilityLeadPayload,
    PublicContactLeadPayload,
)
from schemas_installation_estimate import InstallationEstimateLeadPayload
from services.general_media_storage_service import StoredGeneralMediaObject
from services.installation_estimate_lead_service import (
    InstallationEstimateIncomingFile,
    InstallationEstimateLeadService,
)
from services.private_attachment_storage_service import StoredPrivateObject
from services.public_write_idempotency_service import (
    PublicWriteIdempotencyConflict,
    PublicWriteIdempotencyUnavailable,
    PublicWriteIdempotencyService,
)
from crud.public_write_idempotency import PublicWriteIdempotencyDAO
from services.repair_diagnostic_intake_service import RepairDiagnosticIntakeService
from services.repair_diagnostic_service import (
    RepairDiagnosticIncomingFile,
    RepairDiagnosticLeadPayload,
)
from services.tenant_scope_service import TenantScope
from services.website_lead_service import WebsiteLeadService
from services.website_order_service import WebsiteOrderService


FAMILIES = (
    "checkout",
    "contact",
    "availability",
    "installation",
    "repair",
)
COMMAND_NAMES = {
    "checkout": "public_order_checkout_v1",
    "contact": "public_contact_lead_v1",
    "availability": "public_product_availability_lead_v1",
    "installation": "public_installation_estimate_lead_v1",
    "repair": "public_repair_diagnostic_lead_v1",
}


@dataclass
class FakeGeneralStorage:
    provider_name: str = "test"
    objects: dict[str, bytes] = field(default_factory=dict)
    save_calls: list[str] = field(default_factory=list)
    delete_calls: list[str] = field(default_factory=list)

    async def save_media(self, **kwargs):
        digest = hashlib.sha256(kwargs["content"]).hexdigest()
        path = (
            f"{kwargs['namespace']}/{kwargs['variant_type']}/"
            f"{digest}.{kwargs['extension']}"
        )
        self.save_calls.append(path)
        self.objects[path] = kwargs["content"]
        return StoredGeneralMediaObject(
            url=f"/media/{path}",
            content_hash=digest,
            storage_provider=self.provider_name,
            path=path,
            size_bytes=len(kwargs["content"]),
        )

    async def delete_media(self, path: str):
        self.delete_calls.append(path)
        self.objects.pop(path, None)


@dataclass
class FakePrivateStorage:
    provider_name: str = "test"
    objects: dict[str, bytes] = field(default_factory=dict)
    save_calls: list[str] = field(default_factory=list)
    delete_calls: list[str] = field(default_factory=list)

    async def save(self, *, content, content_hash, extension, content_type, variant):
        del content_type
        key = f"private/{content_hash}/{variant}.{extension}"
        self.save_calls.append(key)
        self.objects[key] = content
        return StoredPrivateObject(
            provider=self.provider_name,
            storage_key=key,
            content_hash=content_hash,
            size_bytes=len(content),
        )

    async def read(self, storage_key):
        return self.objects[storage_key]

    async def exists(self, storage_key):
        return storage_key in self.objects

    async def delete(self, storage_key):
        self.delete_calls.append(storage_key)
        self.objects.pop(storage_key, None)

    async def verify_writable(self):
        return None

    async def presign(self, storage_key, *, expires_seconds, download_name=None):
        del storage_key, expires_seconds, download_name
        return None


@dataclass
class BarrierPrivateStorage(FakePrivateStorage):
    save_barrier: asyncio.Barrier = field(default_factory=lambda: asyncio.Barrier(2))

    async def save(self, **kwargs):
        stored = await super().save(**kwargs)
        await self.save_barrier.wait()
        return stored


def _phone(variant: int) -> str:
    return f"+37529{variant:07d}"


def _content(family: str, variant: int) -> bytes:
    return f"{family}-attachment-{variant}".encode()


async def _invoke(
    family: str,
    session: AsyncSession,
    *,
    scope: TenantScope,
    key: str,
    variant: int,
    product_id: int,
    general_storage: FakeGeneralStorage,
    private_storage: FakePrivateStorage,
):
    if family == "checkout":
        return await WebsiteOrderService.create_order(
            session,
            OrderPayload.model_validate(
                {
                    "customer": {
                        "name": f"Checkout {variant}",
                        "phone": _phone(variant),
                    },
                    "items": [{"product_id": product_id, "quantity": 1}],
                    "comment": f"Checkout request {variant}",
                }
            ),
            tenant_scope=scope,
            idempotency_key=key,
        )
    if family == "contact":
        return await WebsiteLeadService.create_contact_lead(
            session,
            PublicContactLeadPayload(
                name=f"Contact {variant}",
                phone=_phone(variant),
                message=f"Contact request {variant}",
            ),
            tenant_scope=scope,
            idempotency_key=key,
        )
    if family == "availability":
        return await WebsiteLeadService.create_product_availability_lead(
            session,
            ProductAvailabilityLeadPayload(
                product_id=product_id,
                phone=_phone(variant),
                name=f"Availability {variant}",
            ),
            tenant_scope=scope,
            idempotency_key=key,
        )
    if family == "installation":
        content = _content(family, variant)
        return await InstallationEstimateLeadService.create_lead(
            session,
            tenant_scope=scope,
            payload=InstallationEstimateLeadPayload(
                name=f"Installation {variant}",
                phone=_phone(variant),
                description=f"Installation request {variant}",
                consent=True,
            ),
            uploads=[
                InstallationEstimateIncomingFile(
                    category="indoor_unit",
                    filename="room.png",
                    content_type="image/png",
                    content=content,
                    content_hash=hashlib.sha256(content).hexdigest(),
                )
            ],
            idempotency_key=key,
            storage=private_storage,
        )
    if family == "repair":
        content = _content(family, variant)
        response, _, _ = await RepairDiagnosticIntakeService.create_lead(
            session,
            tenant_scope=scope,
            payload=RepairDiagnosticLeadPayload.model_validate(
                {
                    "symptom": "not_cooling",
                    "client_comment": f"Repair request {variant}",
                    "contact": {
                        "name": f"Repair {variant}",
                        "phone": _phone(variant),
                    },
                }
            ),
            uploads={
                "nameplate": [
                    RepairDiagnosticIncomingFile(
                        filename="nameplate.png",
                        content_type="image/png",
                        content=content,
                    )
                ]
            },
            idempotency_key=key,
        )
        return response
    raise AssertionError(f"Unknown family: {family}")


def _resource_id(family: str, response) -> int:
    if family == "checkout":
        return response.id
    if family in {"contact", "availability"}:
        return response.lead_id
    return response.order_id


async def _entity_count(session: AsyncSession, family: str) -> int:
    entity = Lead if family == "contact" else Order
    return int(await session.scalar(select(func.count(entity.id))) or 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("family", FAMILIES)
async def test_public_write_family_full_idempotency_matrix(
    db_engine,
    monkeypatch,
    family,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    general_storage = FakeGeneralStorage()
    private_storage = FakePrivateStorage()
    monkeypatch.setattr(
        "services.repair_diagnostic_intake_service.get_general_media_storage",
        lambda: general_storage,
    )
    async with factory() as setup:
        setup.add(
            Storefront(
                id=2,
                tenant_id=1,
                slug="second",
                display_name="Second",
                status="active",
                is_default=False,
            )
        )
        product = Product(
            title="Idempotency product",
            slug=f"idempotency-{family}",
            price=1200,
            is_published=True,
        )
        setup.add(product)
        await setup.commit()
        await setup.refresh(product)
        product_id = int(product.id or 0)

    first_scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    second_scope = TenantScope(tenant_id=1, storefront_id=2, is_system=True)

    async def call(scope, key, variant):
        async with factory() as session:
            return await _invoke(
                family,
                session,
                scope=scope,
                key=key,
                variant=variant,
                product_id=product_id,
                general_storage=general_storage,
                private_storage=private_storage,
            )

    storage = general_storage if family == "repair" else private_storage
    initial_storage_calls = len(storage.save_calls)
    async with factory() as before_concurrency:
        entity_count_before_concurrency = await _entity_count(
            before_concurrency,
            family,
        )
    barrier = asyncio.Barrier(2)

    async def concurrent_call(worker: int):
        await barrier.wait()
        return await call(
            first_scope,
            f"{family}-concurrent-request-0001",
            100 + worker * 0,
        )

    first, second = await asyncio.gather(concurrent_call(1), concurrent_call(2))
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert _resource_id(family, first) == _resource_id(family, second)
    concurrent_media_writes = len(storage.save_calls) - initial_storage_calls
    if family in {"installation", "repair"}:
        assert concurrent_media_writes == 1
    else:
        assert concurrent_media_writes == 0
    async with factory() as after_concurrency:
        assert (
            await _entity_count(after_concurrency, family)
            == entity_count_before_concurrency + 1
        )

    replay_calls = len(storage.save_calls)
    replay = await call(
        first_scope,
        f"{family}-concurrent-request-0001",
        100,
    )
    assert replay.model_dump(mode="json") == first.model_dump(mode="json")
    assert len(storage.save_calls) == replay_calls

    conflict_key = f"{family}-conflict-request-0001"
    await call(first_scope, conflict_key, 200)
    conflict_storage_calls = len(storage.save_calls)
    with pytest.raises(PublicWriteIdempotencyConflict):
        await call(first_scope, conflict_key, 201)
    assert len(storage.save_calls) == conflict_storage_calls

    cross_key = f"{family}-cross-storefront-0001"
    cross_first = await call(first_scope, cross_key, 300)
    cross_second = await call(second_scope, cross_key, 300)
    assert _resource_id(family, cross_first) != _resource_id(family, cross_second)

    async with factory() as before_failure:
        entity_count_before = await _entity_count(before_failure, family)
    original_complete = PublicWriteIdempotencyService._complete_receipt

    def fail_complete(*_args, **_kwargs):
        raise RuntimeError("forced receipt failure")

    monkeypatch.setattr(
        PublicWriteIdempotencyService,
        "_complete_receipt",
        staticmethod(fail_complete),
    )
    rollback_key = f"{family}-rollback-request-0001"
    rollback_storage_start = len(storage.save_calls)
    with pytest.raises(RuntimeError, match="forced receipt failure"):
        await call(first_scope, rollback_key, 400)
    failed_storage_paths = storage.save_calls[rollback_storage_start:]
    monkeypatch.setattr(
        PublicWriteIdempotencyService,
        "_complete_receipt",
        staticmethod(original_complete),
    )

    async with factory() as after_failure:
        assert await _entity_count(after_failure, family) == entity_count_before
        failed_receipts = await after_failure.scalar(
            select(func.count(PublicWriteIdempotency.id)).where(
                PublicWriteIdempotency.command_name == COMMAND_NAMES[family],
                PublicWriteIdempotency.key_hash
                == PublicWriteIdempotencyService.key_hash(rollback_key),
            )
        )
        assert failed_receipts == 0

    retry_storage_start = len(storage.save_calls)
    retry = await call(first_scope, rollback_key, 400)
    assert _resource_id(family, retry) > 0
    if family in {"installation", "repair"}:
        retry_storage_paths = storage.save_calls[retry_storage_start:]
        assert failed_storage_paths
        assert set(failed_storage_paths).issubset(set(storage.delete_calls))
        assert set(retry_storage_paths).isdisjoint(failed_storage_paths)
        assert set(retry_storage_paths).isdisjoint(storage.delete_calls)
        assert set(retry_storage_paths).issubset(storage.objects)
        if family == "repair":
            expected_prefix = (
                f"public-repair-write/{first_scope.tenant_id}/"
                f"{first_scope.storefront_id}/"
            )
            assert all(path.startswith(expected_prefix) for path in failed_storage_paths)
            assert all(path.startswith(expected_prefix) for path in retry_storage_paths)

    async with factory() as verification:
        receipts = list(
            (
                await verification.execute(
                    select(PublicWriteIdempotency).where(
                        PublicWriteIdempotency.command_name == COMMAND_NAMES[family]
                    )
                )
            ).scalars()
        )
        assert len(receipts) == 5
        assert all(len(receipt.key_hash) == 64 for receipt in receipts)
        assert all(len(receipt.request_fingerprint) == 64 for receipt in receipts)
        assert all(receipt.response_body is not None for receipt in receipts)
        assert all(receipt.response_status == 200 for receipt in receipts)
        assert all(receipt.resource_id is not None for receipt in receipts)
        assert all(receipt.expires_at > receipt.created_at for receipt in receipts)


@pytest.mark.asyncio
@pytest.mark.parametrize("family", FAMILIES)
async def test_public_write_family_returns_unavailable_on_bounded_lock_wait(
    db_engine,
    monkeypatch,
    family,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    general_storage = FakeGeneralStorage()
    private_storage = FakePrivateStorage()
    monkeypatch.setattr(
        "services.repair_diagnostic_intake_service.get_general_media_storage",
        lambda: general_storage,
    )
    monkeypatch.setattr(PublicWriteIdempotencyService, "LOCK_TIMEOUT_MILLISECONDS", 100)
    async with factory() as setup:
        product = Product(
            title=f"Lock timeout {family}",
            slug=f"lock-timeout-{family}",
            price=1200,
            is_published=True,
        )
        setup.add(product)
        await setup.commit()
        await setup.refresh(product)
        product_id = int(product.id or 0)

    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    key = f"{family}-bounded-lock-request-0001"
    async with factory() as holder:
        await PublicWriteIdempotencyDAO.claim(
            holder,
            tenant_scope=scope,
            command_name=COMMAND_NAMES[family],
            key_hash=PublicWriteIdempotencyService.key_hash(key),
            request_fingerprint="f" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        await holder.flush()
        async with factory() as contender:
            with pytest.raises(PublicWriteIdempotencyUnavailable):
                await _invoke(
                    family,
                    contender,
                    scope=scope,
                    key=key,
                    variant=900,
                    product_id=product_id,
                    general_storage=general_storage,
                    private_storage=private_storage,
                )
        await holder.rollback()


@pytest.mark.asyncio
async def test_installation_rollback_cannot_delete_concurrent_success_binary(
    db_engine,
    monkeypatch,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    storage = BarrierPrivateStorage()
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    content = b"same-concurrent-installation-photo"
    upload = InstallationEstimateIncomingFile(
        category="indoor_unit",
        filename="same.png",
        content_type="image/png",
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
    )
    payload = InstallationEstimateLeadPayload(
        name="Concurrent storage",
        phone=_phone(950),
        description="Same bytes, different idempotency keys",
        consent=True,
    )
    original_complete = PublicWriteIdempotencyService._complete_receipt

    def complete_or_fail(receipt, result):
        task = asyncio.current_task()
        if task is not None and task.get_name() == "rollback-installation":
            raise RuntimeError("forced concurrent rollback")
        return original_complete(receipt, result)

    monkeypatch.setattr(
        PublicWriteIdempotencyService,
        "_complete_receipt",
        staticmethod(complete_or_fail),
    )

    async def submit(key: str):
        async with factory() as session:
            return await InstallationEstimateLeadService.create_lead(
                session,
                tenant_scope=scope,
                payload=payload,
                uploads=[upload],
                idempotency_key=key,
                storage=storage,
            )

    rollback_task = asyncio.create_task(
        submit("installation-storage-rollback-0001"),
        name="rollback-installation",
    )
    success_task = asyncio.create_task(
        submit("installation-storage-success-0001"),
        name="success-installation",
    )
    rollback_result, success_result = await asyncio.gather(
        rollback_task,
        success_task,
        return_exceptions=True,
    )

    assert isinstance(rollback_result, RuntimeError)
    assert success_result.order_id > 0
    assert len(set(storage.save_calls)) == 2
    assert len(storage.delete_calls) == 1
    async with factory() as verification:
        attachments = list(
            (await verification.execute(select(ServiceAttachment))).scalars()
        )
        assert len(attachments) == 1
        successful_key = attachments[0].storage_key
        assert successful_key in storage.objects
        assert successful_key not in storage.delete_calls
