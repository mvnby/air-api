from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services.communications.canary import CommunicationsTelegramCanary


EXPECTED_RECIPIENT_KEYS = ("staff:1", "staff:2")
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _runtime(*, complete: bool = False, partial: bool = False) -> dict:
    if complete:
        return {
            "worker_id": "worker",
            "lease_token": "lease-token",
            "lease_expires_at": NOW,
        }
    if partial:
        return {
            "worker_id": "worker",
            "lease_token": None,
            "lease_expires_at": None,
        }
    return {
        "worker_id": None,
        "lease_token": None,
        "lease_expires_at": None,
    }


def _event(
    status: str,
    *,
    dispatcher_owned: bool = False,
    invalid_runtime: bool = False,
):
    if dispatcher_owned:
        runtime = {
            "worker_id": "dispatcher",
            "lease_token": None,
            "lease_expires_at": None,
        }
    elif invalid_runtime:
        runtime = _runtime(complete=True)
    else:
        runtime = _runtime()
    return SimpleNamespace(
        status=status,
        **runtime,
    )


def _delivery(
    status: str,
    recipient_key: str,
    *,
    complete_runtime: bool | None = None,
    partial_runtime: bool = False,
):
    if complete_runtime is None:
        complete_runtime = status == "running" and not partial_runtime
    return SimpleNamespace(
        status=status,
        recipient_key=recipient_key,
        **_runtime(complete=complete_runtime, partial=partial_runtime),
    )


def _classify(event, deliveries):
    return CommunicationsTelegramCanary._classify_lifecycle(
        event,
        deliveries,
        expected_recipient_keys=EXPECTED_RECIPIENT_KEYS,
    )


@pytest.mark.parametrize(
    ("statuses", "expected_state", "expected_outcome"),
    [
        (("queued", "queued"), "pending", None),
        (("sent", "queued"), "pending", None),
        (("dead", "queued"), "pending", None),
        (("sent", "retry"), "pending", None),
        (("sent", "running"), "pending", None),
        (("dead", "running"), "pending", None),
        (("sent", "sent"), "terminal", "success"),
        (("dead", "dead"), "terminal", "dead"),
        (("dead", "canceled"), "terminal", "dead"),
        (("sent", "dead"), "terminal", "partial"),
        (("sent", "canceled"), "terminal", "partial"),
    ],
)
def test_published_delivery_combinations_have_stable_lifecycle(
    statuses,
    expected_state,
    expected_outcome,
):
    lifecycle = _classify(
        _event("published"),
        [
            _delivery(status, EXPECTED_RECIPIENT_KEYS[index])
            for index, status in enumerate(statuses)
        ],
    )

    assert lifecycle.state == expected_state
    assert lifecycle.terminal_outcome == expected_outcome


@pytest.mark.parametrize(
    "recipient_keys",
    [("staff:1",), ("staff:1", "staff:1"), ("staff:1", "staff:3")],
)
def test_published_delivery_topology_must_match_exact_snapshot(recipient_keys):
    lifecycle = _classify(
        _event("published"),
        [_delivery("sent", recipient_key) for recipient_key in recipient_keys],
    )

    assert lifecycle.state == "ambiguous"
    assert lifecycle.terminal_outcome is None


def test_processing_event_requires_worker_only_dispatcher_ownership():
    owned = _classify(_event("processing", dispatcher_owned=True), [])
    missing = _classify(_event("processing"), [])
    invalid_delivery_lease = _classify(
        _event("processing", invalid_runtime=True),
        [],
    )

    assert owned.state == "pending"
    assert missing.state == "ambiguous"
    assert invalid_delivery_lease.state == "ambiguous"


def test_delivery_runtime_ownership_must_match_running_state():
    missing_running_ownership = _classify(
        _event("published"),
        [
            _delivery("running", "staff:1", complete_runtime=False),
            _delivery("queued", "staff:2"),
        ],
    )
    partial_running_ownership = _classify(
        _event("published"),
        [
            _delivery("running", "staff:1", partial_runtime=True),
            _delivery("queued", "staff:2"),
        ],
    )
    stale_sent_ownership = _classify(
        _event("published"),
        [
            _delivery("sent", "staff:1", complete_runtime=True),
            _delivery("sent", "staff:2"),
        ],
    )

    assert missing_running_ownership.state == "ambiguous"
    assert partial_running_ownership.state == "ambiguous"
    assert stale_sent_ownership.state == "ambiguous"


@pytest.mark.parametrize("status", ["pending", "published", "dead"])
def test_nonprocessing_event_with_runtime_ownership_is_ambiguous(status):
    deliveries = (
        [
            _delivery("sent", "staff:1"),
            _delivery("sent", "staff:2"),
        ]
        if status == "published"
        else []
    )
    lifecycle = _classify(
        _event(status, dispatcher_owned=True),
        deliveries,
    )

    assert lifecycle.state == "ambiguous"
    assert lifecycle.terminal_outcome is None
