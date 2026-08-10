from types import SimpleNamespace

import pytest

from bot_app.api_gateway import BotApiUnavailableError
from bot_app.runtime_lease import BotRuntimeLease


@pytest.mark.asyncio
async def test_runtime_lease_acquire_uses_bounded_backoff_on_api_outage(monkeypatch):
    lease = BotRuntimeLease(name="test:bot")
    attempts = 0
    delays: list[float] = []

    async def try_acquire():
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise BotApiUnavailableError("offline")
        return True

    async def sleep(delay):
        delays.append(float(delay))

    monkeypatch.setattr(lease, "try_acquire", try_acquire)
    monkeypatch.setattr("bot_app.runtime_lease.asyncio.sleep", sleep)
    monkeypatch.setattr(
        "bot_app.runtime_lease.settings.BOT_RUNTIME_RETRY_SECONDS", 5
    )
    monkeypatch.setattr(
        "bot_app.runtime_lease.settings.BOT_RUNTIME_LEASE_SECONDS", 45
    )

    await lease.wait_until_acquired()

    assert attempts == 4
    assert delays == [5.0, 10.0, 20.0]


@pytest.mark.asyncio
async def test_runtime_lease_heartbeat_retries_transient_failure(monkeypatch):
    lease = BotRuntimeLease(name="test:bot")
    lease.acquired = True
    lease._record_lease_deadline()
    renew_calls = 0

    class Gateway:
        async def renew_runtime_lease(self, **_kwargs):
            nonlocal renew_calls
            renew_calls += 1
            if renew_calls == 1:
                raise BotApiUnavailableError("offline")
            lease.acquired = False
            return SimpleNamespace(acquired=True)

    async def sleep(_delay):
        return None

    monkeypatch.setattr("bot_app.runtime_lease.get_bot_api_gateway", Gateway)
    monkeypatch.setattr("bot_app.runtime_lease.asyncio.sleep", sleep)

    await lease._heartbeat()

    assert renew_calls == 2
    assert not lease.lost_event.is_set()


@pytest.mark.asyncio
async def test_runtime_lease_heartbeat_stops_before_expiry(monkeypatch):
    lease = BotRuntimeLease(name="test:bot")
    lease.acquired = True
    lease._lease_deadline = 0.0

    class Gateway:
        async def renew_runtime_lease(self, **_kwargs):
            raise BotApiUnavailableError("offline")

    async def sleep(_delay):
        return None

    monkeypatch.setattr("bot_app.runtime_lease.get_bot_api_gateway", Gateway)
    monkeypatch.setattr("bot_app.runtime_lease.asyncio.sleep", sleep)

    await lease._heartbeat()

    assert lease.acquired is False
    assert lease.lost_event.is_set()
