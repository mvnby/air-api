import io

import pytest
from PIL import Image
from sqlmodel import func, select

from models import Order, ServiceAttachment
from services.communications.installation_activation_fence import (
    InstallationEventEnqueueFenceBusy,
)
from services.communications.outbox_service import IntegrationOutboxService
from services.private_attachment_storage_service import StoredPrivateObject


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 24), color=(20, 150, 140)).save(output, format="PNG")
    return output.getvalue()


class FakePrivateStorage:
    provider_name = "local"
    inventory_id = "installation-api-private"

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    async def save(self, *, content, content_hash, extension, content_type, variant):
        key = f"private/{content_hash}/{variant}.{extension}"
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
        self.objects.pop(storage_key, None)

    async def verify_writable(self):
        return None

    async def presign(self, storage_key, *, expires_seconds, download_name=None):
        return None


@pytest.mark.asyncio
async def test_public_installation_estimate_contract_and_replay(
    async_client,
    db,
    monkeypatch,
):
    storage = FakePrivateStorage()
    monkeypatch.setattr(
        "services.installation_estimate_lead_service.get_private_attachment_storage",
        lambda: storage,
    )
    form = {
        "name": "Анна",
        "phone": "+375291112233",
        "email": "anna@example.com",
        "address": "Минск, ул. Ленина, 1",
        "description": "Нужно оценить трассу",
        "object_type": "apartment",
        "consent": "true",
    }
    files = [
        ("indoor_unit", ("indoor.png", _png_bytes(), "image/png")),
        ("route", ("route.png", _png_bytes(), "image/png")),
    ]
    headers = {"Idempotency-Key": "browser-estimate-request-0001"}

    response = await async_client.post(
        "/api/v1/leads/installation-estimate",
        data=form,
        files=files,
        headers=headers,
    )
    replay = await async_client.post(
        "/api/v1/leads/installation-estimate",
        data=form,
        files=files,
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert replay.status_code == 200, replay.text
    assert response.json()["replayed"] is False
    assert replay.json()["replayed"] is False
    assert replay.json()["order_id"] == response.json()["order_id"]
    assert response.json()["attachment_count"] == 2

    unauthorized = await async_client.get(
        f"/api/manager/orders/{response.json()['order_id']}/attachments"
    )
    assert unauthorized.status_code == 401

    order = await db.get(Order, response.json()["order_id"])
    assert order is not None
    assert order.tenant_id == 1
    assert order.storefront_id == 1
    assert order.technical_meta["installation_estimate"]["category_counts"] == {
        "indoor_unit": 1,
        "route": 1,
    }


@pytest.mark.asyncio
async def test_public_installation_estimate_rejects_invalid_file(
    async_client,
):
    response = await async_client.post(
        "/api/v1/leads/installation-estimate",
        data={
            "name": "Анна",
            "phone": "+375291112233",
            "consent": "true",
        },
        files=[
            ("facade", ("facade.txt", b"not-an-image", "text/plain")),
        ],
        headers={"Idempotency-Key": "browser-estimate-request-0002"},
    )

    assert response.status_code == 400
    assert "JPEG, PNG и WebP" in response.json()["detail"]


@pytest.mark.asyncio
async def test_activation_fence_returns_retryable_503_and_rolls_back_intake(
    async_client,
    db,
    monkeypatch,
):
    storage = FakePrivateStorage()
    monkeypatch.setattr(
        "services.installation_estimate_lead_service.get_private_attachment_storage",
        lambda: storage,
    )

    async def busy_enqueue(*args, **kwargs):
        raise InstallationEventEnqueueFenceBusy()

    monkeypatch.setattr(
        IntegrationOutboxService,
        "enqueue",
        busy_enqueue,
    )
    response = await async_client.post(
        "/api/v1/leads/installation-estimate",
        data={
            "name": "Анна",
            "phone": "+375291112233",
            "consent": "true",
        },
        files=[
            ("facade", ("facade.png", _png_bytes(), "image/png")),
        ],
        headers={"Idempotency-Key": "browser-estimate-request-0003"},
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.json() == {
        "detail": "Приём заявки временно занят. Повторите отправку."
    }
    assert await db.scalar(select(func.count(Order.id))) == 0
    assert await db.scalar(select(func.count(ServiceAttachment.id))) == 0
    assert storage.objects
