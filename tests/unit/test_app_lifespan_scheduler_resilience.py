import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import core.app_lifespan as app_lifespan


class FakeRuntimeLock:
    def __init__(self, *, held_results=None, release_error=None):
        self.acquired = True
        self.reason = "test lock acquired"
        self.release_calls = 0
        self.released = asyncio.Event()
        self._held_results = list(held_results or [True])
        self._release_error = release_error

    async def is_held(self):
        if len(self._held_results) > 1:
            return self._held_results.pop(0)
        return self._held_results[0]

    async def release(self):
        self.release_calls += 1
        self.acquired = False
        self.released.set()
        if self._release_error is not None:
            raise self._release_error


class HangingRuntimeLock(FakeRuntimeLock):
    def __init__(self):
        super().__init__()
        self.probe_started = asyncio.Event()
        self.probe_cancelled = asyncio.Event()

    async def is_held(self):
        self.probe_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.probe_cancelled.set()


class UncooperativeProbeRuntimeLock(FakeRuntimeLock):
    def __init__(self):
        super().__init__()
        self.probe_started = asyncio.Event()
        self.cleanup_started = asyncio.Event()
        self.allow_cleanup = asyncio.Event()

    async def is_held(self):
        self.probe_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cleanup_started.set()
            await self.allow_cleanup.wait()
            return False


async def _wait_until(predicate, *, timeout=1.0):
    async def _poll():
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(_poll(), timeout=timeout)


def _enable_scheduler(monkeypatch):
    monkeypatch.setattr(app_lifespan.settings, "APP_ROLE", "primary", raising=False)
    monkeypatch.setattr(app_lifespan.settings, "SCHEDULER_ENABLED", True, raising=False)
    monkeypatch.setattr(app_lifespan, "_bootstrap_database", AsyncMock(return_value=True))
    monkeypatch.setattr(
        app_lifespan,
        "_wait_for_scheduler_lock_fencing",
        AsyncMock(return_value=None),
    )
    fail_stop = Mock()
    monkeypatch.setattr(app_lifespan, "_scheduler_runtime_fail_stop", fail_stop)
    return fail_stop


def _install_controllable_scheduler(monkeypatch):
    started = []
    cancelled = []

    def start(app):
        started_event = asyncio.Event()
        cancelled_event = asyncio.Event()
        started.append(started_event)
        cancelled.append(cancelled_event)

        async def loop():
            started_event.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled_event.set()

        app.state.scheduler_task = asyncio.create_task(loop())
        return True

    monkeypatch.setattr(app_lifespan, "_start_scheduler_loop", start)
    return started, cancelled


@pytest.mark.asyncio
async def test_lock_loss_fail_stops_without_reacquiring(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    monkeypatch.setattr(app_lifespan, "_scheduler_lock_check_seconds", lambda: 0.001)
    retry = AsyncMock(return_value=None)
    monkeypatch.setattr(app_lifespan, "_wait_before_scheduler_retry", retry)
    runtime_lock = FakeRuntimeLock(held_results=[False])
    wait_for_lock = AsyncMock(return_value=runtime_lock)
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        wait_for_lock,
    )
    resume_jobs = AsyncMock(return_value=True)
    monkeypatch.setattr(app_lifespan, "_resume_catalog_import_jobs", resume_jobs)
    started, cancelled = _install_controllable_scheduler(monkeypatch)
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await _wait_until(lambda: fail_stop.call_count == 1)
        await asyncio.wait_for(cancelled[0].wait(), timeout=0.2)
        assert len(started) == 1
        assert cancelled[0].is_set()
        assert runtime_lock.release_calls == 0
        assert wait_for_lock.await_count == 1
        assert resume_jobs.await_count == 1
        assert retry.await_count == 0
        assert app.state.scheduler_runtime["status"] == "faulted"
        assert app.state.scheduler_runtime["reason"] == "ownership_lost"

    assert runtime_lock.release_calls == 1
    fail_stop.assert_called_once_with()


@pytest.mark.asyncio
async def test_hanging_liveness_probe_fail_stops_without_reacquiring(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    monkeypatch.setattr(app_lifespan, "_scheduler_lock_check_seconds", lambda: 0.001)
    monkeypatch.setattr(
        app_lifespan,
        "_scheduler_lock_probe_timeout_seconds",
        lambda: 0.001,
    )
    monkeypatch.setattr(
        app_lifespan,
        "_wait_before_scheduler_retry",
        AsyncMock(return_value=None),
    )
    hanging_lock = HangingRuntimeLock()
    wait_for_lock = AsyncMock(return_value=hanging_lock)
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        wait_for_lock,
    )
    resume_jobs = AsyncMock(return_value=True)
    monkeypatch.setattr(app_lifespan, "_resume_catalog_import_jobs", resume_jobs)
    started, cancelled = _install_controllable_scheduler(monkeypatch)
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await _wait_until(lambda: fail_stop.call_count == 1)
        await asyncio.wait_for(cancelled[0].wait(), timeout=0.2)
        assert hanging_lock.probe_started.is_set()
        assert hanging_lock.probe_cancelled.is_set()
        assert cancelled[0].is_set()
        assert hanging_lock.release_calls == 0
        assert wait_for_lock.await_count == 1
        assert resume_jobs.await_count == 1
        assert app.state.scheduler_runtime["status"] == "faulted"
        assert app.state.scheduler_runtime["reason"] == "ownership_lost"

    assert hanging_lock.release_calls == 1
    fail_stop.assert_called_once_with()


@pytest.mark.asyncio
async def test_probe_timeout_does_not_wait_for_stuck_cancellation_cleanup(monkeypatch):
    monkeypatch.setattr(app_lifespan, "_scheduler_lock_check_seconds", lambda: 0.001)
    monkeypatch.setattr(
        app_lifespan,
        "_scheduler_lock_probe_timeout_seconds",
        lambda: 0.001,
    )
    runtime_lock = UncooperativeProbeRuntimeLock()

    async def loop():
        await asyncio.Event().wait()

    scheduler_task = asyncio.create_task(loop())
    try:
        with pytest.raises(app_lifespan.SchedulerOwnershipLost):
            await asyncio.wait_for(
                app_lifespan._monitor_scheduler_runtime_lock(
                    scheduler_task,
                    runtime_lock,
                ),
                timeout=0.05,
        )
        assert runtime_lock.probe_started.is_set()
        await asyncio.wait_for(runtime_lock.cleanup_started.wait(), timeout=0.05)
    finally:
        runtime_lock.allow_cleanup.set()
        scheduler_task.cancel()
        await asyncio.gather(scheduler_task, return_exceptions=True)
        await _wait_until(
            lambda: not app_lifespan._detached_scheduler_probe_tasks
        )


@pytest.mark.asyncio
async def test_acquire_exception_retries_then_starts_scheduler(monkeypatch):
    _enable_scheduler(monkeypatch)
    retry = AsyncMock(return_value=None)
    monkeypatch.setattr(app_lifespan, "_wait_before_scheduler_retry", retry)
    runtime_lock = FakeRuntimeLock()
    wait_for_lock = AsyncMock(
        side_effect=[ConnectionError("database unavailable"), runtime_lock]
    )
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        wait_for_lock,
    )
    monkeypatch.setattr(
        app_lifespan,
        "_resume_catalog_import_jobs",
        AsyncMock(return_value=True),
    )
    started, _cancelled = _install_controllable_scheduler(monkeypatch)
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await _wait_until(lambda: len(started) == 1)
        await asyncio.wait_for(started[0].wait(), timeout=0.2)
        assert wait_for_lock.await_count == 2
        retry.assert_awaited_once_with()

    assert runtime_lock.release_calls == 1


@pytest.mark.asyncio
async def test_release_failure_does_not_stop_reacquisition(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    monkeypatch.setattr(
        app_lifespan,
        "_wait_before_scheduler_retry",
        AsyncMock(return_value=None),
    )
    first_lock = FakeRuntimeLock(
        release_error=ConnectionError("unlock failed"),
    )
    second_lock = FakeRuntimeLock()
    wait_for_lock = AsyncMock(side_effect=[first_lock, second_lock])
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        wait_for_lock,
    )
    monkeypatch.setattr(
        app_lifespan,
        "_resume_catalog_import_jobs",
        AsyncMock(return_value=True),
    )
    start_calls = 0
    started = asyncio.Event()

    def start(app):
        nonlocal start_calls
        start_calls += 1
        if start_calls == 1:
            return False

        async def loop():
            started.set()
            await asyncio.Event().wait()

        app.state.scheduler_task = asyncio.create_task(loop())
        return True

    monkeypatch.setattr(app_lifespan, "_start_scheduler_loop", start)
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=0.2)
        assert first_lock.release_calls == 1
        assert wait_for_lock.await_count == 2
        assert start_calls == 2
        fail_stop.assert_not_called()

    assert second_lock.release_calls == 1


@pytest.mark.asyncio
async def test_shutdown_cancels_supervisor_during_retry_backoff(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    retry_started = asyncio.Event()
    retry_cancelled = asyncio.Event()

    async def wait_for_retry():
        retry_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            retry_cancelled.set()

    monkeypatch.setattr(app_lifespan, "_wait_before_scheduler_retry", wait_for_retry)
    acquire = AsyncMock(side_effect=ConnectionError("database unavailable"))
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        acquire,
    )
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await asyncio.wait_for(retry_started.wait(), timeout=0.2)
        assert acquire.await_count == 1

    assert retry_cancelled.is_set()
    assert acquire.await_count == 1
    assert app.state.scheduler_supervisor_task is None
    fail_stop.assert_not_called()


@pytest.mark.asyncio
async def test_active_scheduler_shutdown_fail_stops_before_cancel_and_unlock(
    monkeypatch,
):
    fail_stop = _enable_scheduler(monkeypatch)
    events = []
    fail_stop.side_effect = lambda: events.append("fail_stop")
    runtime_lock = FakeRuntimeLock()
    original_release = runtime_lock.release

    async def release_in_order():
        events.append("lock_release")
        await original_release()

    runtime_lock.release = release_in_order
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        AsyncMock(return_value=runtime_lock),
    )
    monkeypatch.setattr(
        app_lifespan,
        "_resume_catalog_import_jobs",
        AsyncMock(return_value=True),
    )
    scheduler_started = asyncio.Event()

    def start(app):
        async def loop():
            scheduler_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                events.append("scheduler_cancel")

        app.state.scheduler_task = asyncio.create_task(loop())
        return True

    monkeypatch.setattr(app_lifespan, "_start_scheduler_loop", start)
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await asyncio.wait_for(scheduler_started.wait(), timeout=0.2)
        await _wait_until(
            lambda: app.state.scheduler_runtime["status"] == "running"
        )

    fail_stop.assert_called_once_with()
    assert events == ["fail_stop", "scheduler_cancel", "lock_release"]
    assert runtime_lock.release_calls == 1
    assert app.state.scheduler_work_started is False


@pytest.mark.asyncio
async def test_shutdown_fail_stops_cancelled_scheduler_before_unlock(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    events = []
    fail_stop.side_effect = lambda: events.append("fail_stop")
    runtime_lock = FakeRuntimeLock()
    original_release = runtime_lock.release

    async def release_in_order():
        events.append("lock_release")
        await original_release()

    runtime_lock.release = release_in_order
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        AsyncMock(return_value=runtime_lock),
    )
    monkeypatch.setattr(
        app_lifespan,
        "_resume_catalog_import_jobs",
        AsyncMock(return_value=True),
    )
    monitor_started = asyncio.Event()

    def start(app):
        async def loop():
            try:
                await asyncio.Event().wait()
            finally:
                events.append("scheduler_cancel")

        app.state.scheduler_task = asyncio.create_task(loop())
        return True

    async def hold_monitor(_scheduler_task, _runtime_lock):
        monitor_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(app_lifespan, "_start_scheduler_loop", start)
    monkeypatch.setattr(
        app_lifespan,
        "_monitor_scheduler_runtime_lock",
        hold_monitor,
    )
    app = SimpleNamespace(state=SimpleNamespace())
    lifespan = app_lifespan.app_lifespan(app)
    await lifespan.__aenter__()

    await asyncio.wait_for(monitor_started.wait(), timeout=0.2)
    scheduler_task = app.state.scheduler_task
    scheduler_task.cancel()
    await asyncio.gather(scheduler_task, return_exceptions=True)
    assert scheduler_task.done()
    assert scheduler_task.cancelled()
    assert app.state.scheduler_work_started is True
    assert runtime_lock.acquired is True

    await lifespan.__aexit__(None, None, None)

    fail_stop.assert_called_once_with()
    assert events == ["scheduler_cancel", "fail_stop", "lock_release"]
    assert runtime_lock.release_calls == 1
    assert app.state.scheduler_work_started is False


@pytest.mark.asyncio
async def test_shutdown_during_fencing_releases_lock_without_fail_stop(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    fencing_started = asyncio.Event()
    fencing_cancelled = asyncio.Event()

    async def wait_during_fencing(_runtime_lock):
        fencing_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            fencing_cancelled.set()

    monkeypatch.setattr(
        app_lifespan,
        "_wait_for_scheduler_lock_fencing",
        wait_during_fencing,
    )
    runtime_lock = FakeRuntimeLock()
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        AsyncMock(return_value=runtime_lock),
    )
    resume_jobs = AsyncMock()
    start_loop = Mock()
    monkeypatch.setattr(app_lifespan, "_resume_catalog_import_jobs", resume_jobs)
    monkeypatch.setattr(app_lifespan, "_start_scheduler_loop", start_loop)
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await asyncio.wait_for(fencing_started.wait(), timeout=0.2)
        assert app.state.scheduler_runtime["status"] == "fencing"
        assert getattr(app.state, "scheduler_task", None) is None

    fail_stop.assert_not_called()
    assert fencing_cancelled.is_set()
    assert runtime_lock.release_calls == 1
    resume_jobs.assert_not_awaited()
    start_loop.assert_not_called()


@pytest.mark.asyncio
async def test_supervisor_cancel_during_child_cleanup_releases_lock_without_retry(
    monkeypatch,
):
    _enable_scheduler(monkeypatch)
    monkeypatch.setattr(app_lifespan, "_scheduler_lock_check_seconds", lambda: 0.001)
    runtime_lock = FakeRuntimeLock(held_results=[False])
    acquire = AsyncMock(return_value=runtime_lock)
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        acquire,
    )
    monkeypatch.setattr(
        app_lifespan,
        "_resume_catalog_import_jobs",
        AsyncMock(return_value=True),
    )
    child_started = asyncio.Event()
    child_cleanup_started = asyncio.Event()
    child_cleanup_finished = asyncio.Event()
    retry_called = asyncio.Event()

    def start(app):
        async def loop():
            child_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                child_cleanup_started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    child_cleanup_finished.set()

        app.state.scheduler_task = asyncio.create_task(loop())
        return True

    async def unexpected_retry():
        retry_called.set()

    monkeypatch.setattr(app_lifespan, "_start_scheduler_loop", start)
    monkeypatch.setattr(app_lifespan, "_wait_before_scheduler_retry", unexpected_retry)
    app = SimpleNamespace(state=SimpleNamespace())
    lifespan = app_lifespan.app_lifespan(app)
    await lifespan.__aenter__()

    try:
        await asyncio.wait_for(child_started.wait(), timeout=0.2)
        await asyncio.wait_for(child_cleanup_started.wait(), timeout=0.2)
        supervisor_task = app.state.scheduler_supervisor_task
        supervisor_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(supervisor_task, timeout=0.2)

        assert supervisor_task.done()
        assert child_cleanup_finished.is_set()
        assert runtime_lock.release_calls == 1
        assert acquire.await_count == 1
        assert retry_called.is_set() is False
    finally:
        await lifespan.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_external_cancel_during_supervisor_shutdown_is_not_swallowed():
    cleanup_started = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def supervisor():
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_finished.set()

    supervisor_task = asyncio.create_task(supervisor())
    app = SimpleNamespace(
        state=SimpleNamespace(scheduler_supervisor_task=supervisor_task)
    )
    stop_task = asyncio.create_task(app_lifespan._stop_scheduler_supervisor(app))
    await asyncio.wait_for(cleanup_started.wait(), timeout=0.2)

    stop_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(stop_task, timeout=0.2)

    assert cleanup_finished.is_set()
    assert supervisor_task.done()
    assert app.state.scheduler_supervisor_task is None
    assert app.state.scheduler_runtime["status"] == "stopped"
