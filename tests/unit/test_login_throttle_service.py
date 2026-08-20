from datetime import datetime, timedelta, timezone

from services.login_throttle_service import LoginThrottleService


def test_login_throttle_fingerprint_is_normalized_and_non_reversible() -> None:
    fingerprint = LoginThrottleService.fingerprint("  Manager@Example.COM ")

    assert fingerprint == LoginThrottleService.fingerprint("manager@example.com")
    assert len(fingerprint) == 64
    assert "manager" not in fingerprint
    assert "example" not in fingerprint


def test_empty_username_fingerprint_cannot_collide_with_literal_sentinel() -> None:
    assert LoginThrottleService.fingerprint(None) == LoginThrottleService.fingerprint("   ")
    assert LoginThrottleService.fingerprint(None) != LoginThrottleService.fingerprint("<empty>")


def test_global_fingerprint_is_separate_from_every_account_fingerprint() -> None:
    assert LoginThrottleService.global_fingerprint() != LoginThrottleService.fingerprint(
        "manager"
    )


def test_source_fingerprints_use_a_bounded_secret_bucket_space(monkeypatch) -> None:
    monkeypatch.setattr(LoginThrottleService, "SOURCE_BUCKET_COUNT", 4)

    fingerprints = {
        LoginThrottleService.source_fingerprint(f"192.0.2.{index}")
        for index in range(100)
    }

    assert 1 < len(fingerprints) <= 4
    assert LoginThrottleService.global_fingerprint() not in fingerprints
    assert LoginThrottleService.fingerprint("manager") not in fingerprints


def test_login_throttle_retry_after_rounds_up_and_never_returns_zero() -> None:
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)

    assert LoginThrottleService._retry_after(
        now + timedelta(seconds=1, microseconds=1),
        now,
    ) == 2
    assert LoginThrottleService._retry_after(now, now) == 1
