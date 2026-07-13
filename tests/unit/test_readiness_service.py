from services.readiness_service import ReadinessService


def test_scheduler_runtime_payload_accepts_only_allowlisted_snapshot(monkeypatch):
    monkeypatch.setattr(
        "services.readiness_service.settings.APP_ROLE",
        "primary",
        raising=False,
    )
    monkeypatch.setattr(
        "services.readiness_service.settings.SCHEDULER_ENABLED",
        True,
        raising=False,
    )
    valid = {
        "expected": True,
        "status": "running",
        "reason": "scheduler_loop_running",
        "changed_at": "2026-07-13T08:00:00+00:00",
    }
    assert ReadinessService._scheduler_runtime_payload(valid) == valid

    unsafe = {
        **valid,
        "reason": "database password leaked in raw exception",
        "changed_at": "not-a-timestamp",
    }
    sanitized = ReadinessService._scheduler_runtime_payload(unsafe)
    assert sanitized["expected"] is True
    assert sanitized["status"] == "waiting_lock"
    assert sanitized["reason"] == "runtime_state_unavailable"
    assert sanitized["changed_at"] is None
    assert "password" not in str(sanitized)
