import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import core.app_lifespan as app_lifespan


REAL_WAIT_FOR_SCHEDULER_LOCK_FENCING = (
    app_lifespan._wait_for_scheduler_lock_fencing
)


class FakeRuntimeLock:
    def __init__(self, *, on_release=None, held_results=None, release_error=None):
        self.acquired = True
        self.reason = "test lock acquired"
        self.release_calls = 0
        self.is_held_calls = 0
        self.released = asyncio.Event()
        self._on_release = on_release
        self._held_results = list(held_results or [True])
        self._release_error = release_error

    async def is_held(self):
        self.is_held_calls += 1
        if len(self._held_results) > 1:
            return self._held_results.pop(0)
        return self._held_results[0]

    async def release(self):
        self.release_calls += 1
        self.acquired = False
        if self._on_release is not None:
            await self._on_release(self)
        self.released.set()
        if self._release_error is not None:
            raise self._release_error


class HangingRuntimeLock(FakeRuntimeLock):
    def __init__(self):
        super().__init__()
        self.probe_started = asyncio.Event()
        self.probe_cancelled = asyncio.Event()

    async def is_held(self):
        self.is_held_calls += 1
        self.probe_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.probe_cancelled.set()


class ExclusiveLockPool:
    def __init__(self):
        self._condition = asyncio.Condition()
        self._owner = None
        self.locks = []

    async def wait_until_acquired(self, _session_factory, _lock_name, **_kwargs):
        async with self._condition:
            await self._condition.wait_for(lambda: self._owner is None)
            lock = FakeRuntimeLock(on_release=self._release)
            self._owner = lock
            self.locks.append(lock)
            return lock

    async def _release(self, lock):
        async with self._condition:
            if self._owner is lock:
                self._owner = None
                self._condition.notify_all()

    async def revoke_owner(self):
        async with self._condition:
            if self._owner is None:
                return
            self._owner._held_results = [False]
            self._owner = None
            self._condition.notify_all()


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


def test_scheduler_lock_check_interval_is_bounded_separately_from_retry(monkeypatch):
    monkeypatch.setattr(
        app_lifespan.settings,
        "RUNTIME_LOCK_RETRY_SECONDS",
        15,
        raising=False,
    )
    assert app_lifespan._scheduler_runtime_retry_seconds() == 15
    assert app_lifespan._scheduler_lock_check_seconds() == 5
    assert app_lifespan._scheduler_lock_probe_timeout_seconds() == 3
    assert app_lifespan._scheduler_lock_fencing_grace_seconds() == 12

    monkeypatch.setattr(
        app_lifespan.settings,
        "RUNTIME_LOCK_RETRY_SECONDS",
        2,
        raising=False,
    )
    assert app_lifespan._scheduler_runtime_retry_seconds() == 2
    assert app_lifespan._scheduler_lock_check_seconds() == 2
    assert app_lifespan._scheduler_lock_probe_timeout_seconds() == 2
    assert app_lifespan._scheduler_lock_fencing_grace_seconds() == 12

    monkeypatch.setattr(
        app_lifespan.settings,
        "RUNTIME_LOCK_RETRY_SECONDS",
        -3,
        raising=False,
    )
    assert app_lifespan._scheduler_runtime_retry_seconds() == 1
    assert app_lifespan._scheduler_lock_check_seconds() == 1
    assert app_lifespan._scheduler_lock_probe_timeout_seconds() == 1
    assert app_lifespan._scheduler_lock_fencing_grace_seconds() == 12


@pytest.mark.asyncio
async def test_overlapping_apps_reacquire_scheduler_after_owner_releases(monkeypatch):
    _enable_scheduler(monkeypatch)
    pool = ExclusiveLockPool()
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        pool.wait_until_acquired,
    )
    resume_jobs = AsyncMock(return_value=True)
    monkeypatch.setattr(app_lifespan, "_resume_catalog_import_jobs", resume_jobs)
    started, cancelled = _install_controllable_scheduler(monkeypatch)

    first_app = SimpleNamespace(state=SimpleNamespace())
    second_app = SimpleNamespace(state=SimpleNamespace())
    first_lifespan = app_lifespan.app_lifespan(first_app)
    second_lifespan = app_lifespan.app_lifespan(second_app)
    first_entered = second_entered = False

    try:
        await asyncio.wait_for(first_lifespan.__aenter__(), timeout=0.2)
        first_entered = True
        await _wait_until(lambda: len(started) == 1)
        await asyncio.wait_for(started[0].wait(), timeout=0.2)

        # The overlapping API becomes ready even while its supervisor waits.
        await asyncio.wait_for(second_lifespan.__aenter__(), timeout=0.2)
        second_entered = True
        await asyncio.sleep(0)
        assert len(started) == 1

        await first_lifespan.__aexit__(None, None, None)
        first_entered = False
        await _wait_until(lambda: len(started) == 2)
        await asyncio.wait_for(started[1].wait(), timeout=0.2)

        assert resume_jobs.await_count == 2
        assert len(pool.locks) == 2
        assert pool.locks[0].release_calls == 1
        assert cancelled[0].is_set()
    finally:
        if first_entered:
            await first_lifespan.__aexit__(None, None, None)
        if second_entered:
            await second_lifespan.__aexit__(None, None, None)

    assert pool.locks[1].release_calls == 1
    assert cancelled[1].is_set()


@pytest.mark.asyncio
async def test_fencing_prevents_two_apps_from_overlapping_after_server_lock_loss(
    monkeypatch,
):
    _enable_scheduler(monkeypatch)
    monkeypatch.setattr(
        app_lifespan,
        "_wait_for_scheduler_lock_fencing",
        REAL_WAIT_FOR_SCHEDULER_LOCK_FENCING,
    )
    monkeypatch.setattr(app_lifespan, "_scheduler_lock_check_seconds", lambda: 0.001)
    monkeypatch.setattr(
        app_lifespan,
        "_scheduler_lock_probe_timeout_seconds",
        lambda: 0.001,
    )
    monkeypatch.setattr(
        app_lifespan,
        "_scheduler_lock_fencing_grace_seconds",
        lambda: 0.01,
    )
    pool = ExclusiveLockPool()
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        pool.wait_until_acquired,
    )
    resume_jobs = AsyncMock(return_value=True)
    monkeypatch.setattr(app_lifespan, "_resume_catalog_import_jobs", resume_jobs)
    started = []
    cancelled = []
    active_loops = 0
    maximum_active_loops = 0

    def start(app):
        started_event = asyncio.Event()
        cancelled_event = asyncio.Event()
        started.append(started_event)
        cancelled.append(cancelled_event)

        async def loop():
            nonlocal active_loops, maximum_active_loops
            active_loops += 1
            maximum_active_loops = max(maximum_active_loops, active_loops)
            started_event.set()
            try:
                await asyncio.Event().wait()
            finally:
                active_loops -= 1
                cancelled_event.set()

        app.state.scheduler_task = asyncio.create_task(loop())
        return True

    monkeypatch.setattr(app_lifespan, "_start_scheduler_loop", start)
    first_app = SimpleNamespace(state=SimpleNamespace())
    second_app = SimpleNamespace(state=SimpleNamespace())
    first_lifespan = app_lifespan.app_lifespan(first_app)
    second_lifespan = app_lifespan.app_lifespan(second_app)
    first_entered = second_entered = False

    try:
        await first_lifespan.__aenter__()
        first_entered = True
        await _wait_until(lambda: len(started) == 1)
        await asyncio.wait_for(started[0].wait(), timeout=0.2)

        await second_lifespan.__aenter__()
        second_entered = True
        await pool.revoke_owner()
        await _wait_until(lambda: len(started) == 2)
        await asyncio.wait_for(started[1].wait(), timeout=0.2)

        assert cancelled[0].is_set()
        assert maximum_active_loops == 1
        assert resume_jobs.await_count == 2
    finally:
        if first_entered:
            await first_lifespan.__aexit__(None, None, None)
        if second_entered:
            await second_lifespan.__aexit__(None, None, None)

    assert cancelled[1].is_set()
    assert maximum_active_loops == 1


@pytest.mark.asyncio
async def test_shutdown_cancels_scheduler_supervisor_before_lock_acquire(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    waiting = asyncio.Event()
    waiter_cancelled = asyncio.Event()

    async def wait_forever(_session_factory, _lock_name, **_kwargs):
        waiting.set()
        try:
            await asyncio.Event().wait()
        finally:
            waiter_cancelled.set()

    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        wait_forever,
    )
    resume_jobs = AsyncMock()
    start_loop = Mock()
    monkeypatch.setattr(app_lifespan, "_resume_catalog_import_jobs", resume_jobs)
    monkeypatch.setattr(app_lifespan, "_start_scheduler_loop", start_loop)
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await asyncio.wait_for(waiting.wait(), timeout=0.2)
        assert app.state.scheduler_supervisor_task.done() is False
        assert app.state.scheduler_runtime["expected"] is True
        assert app.state.scheduler_runtime["status"] == "waiting_lock"

    assert waiter_cancelled.is_set()
    resume_jobs.assert_not_awaited()
    start_loop.assert_not_called()
    fail_stop.assert_not_called()
    assert app.state.scheduler_supervisor_task is None
    assert app.state.scheduler_runtime["status"] == "stopped"


@pytest.mark.asyncio
async def test_scheduler_supervisor_starts_once_and_cleans_up(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    runtime_lock = FakeRuntimeLock()
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
        await _wait_until(lambda: len(started) == 1)
        await asyncio.wait_for(started[0].wait(), timeout=0.2)
        assert app.state.scheduler_runtime_lock is runtime_lock
        assert app.state.scheduler_runtime["expected"] is True
        assert app.state.scheduler_runtime["status"] == "running"
        assert app.state.scheduler_runtime["reason"] == "scheduler_loop_running"
        assert app.state.scheduler_runtime["changed_at"].endswith("+00:00")
        resume_jobs.assert_awaited_once_with()
        wait_for_lock.assert_awaited_once_with(
            app_lifespan.async_session_maker,
            "mvn:scheduler",
            required=True,
        )
        supervisor_task = app.state.scheduler_supervisor_task
        assert app_lifespan._start_scheduler_supervisor(app) is False
        assert app.state.scheduler_supervisor_task is supervisor_task
        assert app.state.scheduler_work_started is True

    assert cancelled[0].is_set()
    fail_stop.assert_called_once_with()
    assert runtime_lock.release_calls == 1
    assert app.state.scheduler_task is None
    assert app.state.scheduler_runtime_lock is None
    assert app.state.scheduler_supervisor_task is None
    assert app.state.scheduler_runtime["status"] == "stopped"


@pytest.mark.asyncio
async def test_disabled_scheduler_exposes_disabled_runtime_state(monkeypatch):
    monkeypatch.setattr(app_lifespan.settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(
        app_lifespan.settings,
        "SCHEDULER_ENABLED",
        False,
        raising=False,
    )
    monkeypatch.setattr(app_lifespan, "_bootstrap_database", AsyncMock(return_value=False))
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        assert app.state.scheduler_runtime["expected"] is False
        assert app.state.scheduler_runtime["status"] == "disabled"
        assert app.state.scheduler_runtime["reason"] == "runtime_control_disabled"

    assert app.state.scheduler_runtime["status"] == "disabled"


@pytest.mark.asyncio
async def test_scheduler_supervisor_releases_lock_when_resume_fails(monkeypatch):
    _enable_scheduler(monkeypatch)
    monkeypatch.setattr(
        app_lifespan,
        "_wait_before_scheduler_retry",
        AsyncMock(return_value=None),
    )
    failed_lock = FakeRuntimeLock()
    recovered_lock = FakeRuntimeLock()
    wait_for_lock = AsyncMock(side_effect=[failed_lock, recovered_lock])
    monkeypatch.setattr(
        app_lifespan.RuntimeLockService,
        "wait_until_acquired",
        wait_for_lock,
    )
    resume_jobs = AsyncMock(side_effect=[RuntimeError("resume failed"), True])
    monkeypatch.setattr(
        app_lifespan,
        "_resume_catalog_import_jobs",
        resume_jobs,
    )
    started, _cancelled = _install_controllable_scheduler(monkeypatch)
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await _wait_until(lambda: len(started) == 1)
        await asyncio.wait_for(started[0].wait(), timeout=0.2)
        assert app.state.scheduler_supervisor_task.done() is False
        assert wait_for_lock.await_count == 2
        assert resume_jobs.await_count == 2
        assert failed_lock.release_calls == 1

    assert recovered_lock.release_calls == 1
    assert app.state.scheduler_runtime_lock is None


@pytest.mark.asyncio
async def test_scheduler_loop_failure_after_start_fail_stops_without_retry(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    runtime_lock = FakeRuntimeLock()
    wait_for_lock = AsyncMock(return_value=runtime_lock)
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
    loop_calls = 0

    async def start_loop(*, interval_hours):
        nonlocal loop_calls
        assert interval_hours == app_lifespan.settings.SCHEDULER_INTERVAL
        loop_calls += 1
        raise RuntimeError("scheduler failed")

    monkeypatch.setitem(
        sys.modules,
        "services.scheduler_service",
        SimpleNamespace(scheduler_service=SimpleNamespace(start_loop=start_loop)),
    )
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await _wait_until(lambda: fail_stop.call_count == 1)
        assert app.state.scheduler_supervisor_task.done() is False
        assert wait_for_lock.await_count == 1
        assert runtime_lock.release_calls == 0
        assert app.state.scheduler_runtime["status"] == "faulted"
        assert app.state.scheduler_runtime["reason"] == "scheduler_loop_failed"

    assert loop_calls == 1
    fail_stop.assert_called_once_with()
    assert runtime_lock.release_calls == 1
    assert app.state.scheduler_task is None
    assert app.state.scheduler_runtime_lock is None


@pytest.mark.asyncio
async def test_scheduler_loop_failure_after_running_fail_stops_without_retry(monkeypatch):
    fail_stop = _enable_scheduler(monkeypatch)
    runtime_lock = FakeRuntimeLock()
    wait_for_lock = AsyncMock(return_value=runtime_lock)
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
    loop_started = asyncio.Event()
    fail_loop = asyncio.Event()

    async def start_loop(*, interval_hours):
        assert interval_hours == app_lifespan.settings.SCHEDULER_INTERVAL
        loop_started.set()
        await fail_loop.wait()
        raise RuntimeError("scheduler failed after startup")

    monkeypatch.setitem(
        sys.modules,
        "services.scheduler_service",
        SimpleNamespace(scheduler_service=SimpleNamespace(start_loop=start_loop)),
    )
    app = SimpleNamespace(state=SimpleNamespace())

    async with app_lifespan.app_lifespan(app):
        await asyncio.wait_for(loop_started.wait(), timeout=0.2)
        await _wait_until(lambda: app.state.scheduler_runtime["status"] == "running")
        fail_loop.set()
        await _wait_until(lambda: fail_stop.call_count == 1)
        assert wait_for_lock.await_count == 1
        assert app.state.scheduler_runtime["status"] == "faulted"
        assert app.state.scheduler_runtime["reason"] == "scheduler_loop_failed"

    fail_stop.assert_called_once_with()
    assert runtime_lock.release_calls == 1


@pytest.mark.asyncio
async def test_catalog_resume_false_is_rechecked_until_safe(monkeypatch):
    resume_jobs = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(app_lifespan, "_resume_catalog_import_jobs", resume_jobs)
    app = SimpleNamespace(state=SimpleNamespace())

    assert await app_lifespan._resume_catalog_import_jobs_once(app) is False
    assert getattr(app.state, "catalog_import_jobs_resumed", False) is False

    assert await app_lifespan._resume_catalog_import_jobs_once(app) is True
    assert app.state.catalog_import_jobs_resumed is True

    assert await app_lifespan._resume_catalog_import_jobs_once(app) is False
    assert resume_jobs.await_count == 2
