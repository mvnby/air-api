import asyncio

import pytest

from services import scheduler_service
from services.installation_preview_retention_service import InstallationPreviewRetentionService
from services.public_write_idempotency_retention_service import PublicWriteIdempotencyRetentionService


@pytest.mark.asyncio
@pytest.mark.parametrize("preview_batches,receipt_batches,expected_sleeps,expected_commits", [
    ([1000, 1000, 250], [0, 0, 0], [1, 1, 3600], 3),
    ([0], [0], [3600], 1),
    ([0, 0], [1000, 25], [1, 3600], 2),
])
async def test_retention_catches_up_in_bounded_commits_then_sleeps(
    monkeypatch, preview_batches, receipt_batches, expected_sleeps, expected_commits,
):
    commits = []
    sleeps = []
    limits = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            commits.append(True)

    async def delete_previews(_session, *, limit):
        limits.append(limit)
        return preview_batches.pop(0)

    async def delete_receipts(_session, *, limit):
        limits.append(limit)
        return receipt_batches.pop(0)

    async def record_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == len(expected_sleeps):
            raise asyncio.CancelledError

    monkeypatch.setattr(scheduler_service, "async_session_maker", Session)
    monkeypatch.setattr(InstallationPreviewRetentionService, "delete_expired_batch", delete_previews)
    monkeypatch.setattr(PublicWriteIdempotencyRetentionService, "delete_expired_batch", delete_receipts)
    monkeypatch.setattr(scheduler_service.asyncio, "sleep", record_sleep)

    with pytest.raises(asyncio.CancelledError):
        await scheduler_service.SchedulerService._public_write_receipt_retention_loop(None)
    assert sleeps == expected_sleeps
    assert len(commits) == expected_commits
    assert limits == [1000] * (expected_commits * 2)


@pytest.mark.asyncio
async def test_retention_error_uses_backoff_without_busy_spin(monkeypatch):
    sleeps = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    async def fail(_session, *, limit):
        raise RuntimeError("temporary database error")

    async def record_sleep(seconds):
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(scheduler_service, "async_session_maker", Session)
    monkeypatch.setattr(PublicWriteIdempotencyRetentionService, "delete_expired_batch", fail)
    monkeypatch.setattr(scheduler_service.asyncio, "sleep", record_sleep)

    with pytest.raises(asyncio.CancelledError):
        await scheduler_service.SchedulerService._public_write_receipt_retention_loop(None)
    assert sleeps == [300]
