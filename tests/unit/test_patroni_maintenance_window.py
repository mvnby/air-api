import json
import subprocess

import pytest

from scripts.ha import patroni_maintenance_window as maintenance


def _result(payload: dict, *, returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(
        ["ssh"],
        returncode,
        json.dumps(payload),
        stderr,
    )


def _active(label: str, *, transaction_id: str = "a" * 32, mtime_ns: int = 10**12):
    return maintenance.NodeObservation(
        label=label,
        status="active",
        transaction_id=transaction_id,
        mtime_ns=mtime_ns,
    )


def test_parse_observation_accepts_only_attested_active_payload():
    payload = {
        "status": "active",
        "transaction_id": "b" * 32,
        "mtime_ns": 123,
        "role_agent_state": "active",
        "timer_states": {
            "mvn-postgres-wal-upload.timer": "inactive",
            "mvn-postgres-basebackup.timer": "inactive",
        },
    }

    observation = maintenance.parse_observation("api", _result(payload))

    assert observation == maintenance.NodeObservation(
        label="api",
        status="active",
        transaction_id="b" * 32,
        mtime_ns=123,
    )


@pytest.mark.parametrize(
    "payload, match",
    [
        ({"status": "invalid", "error": "marker unsafe"}, "marker unsafe"),
        (
            {
                "status": "active",
                "transaction_id": "c" * 32,
                "mtime_ns": 123,
                "role_agent_state": "inactive",
                "timer_states": {
                    "mvn-postgres-wal-upload.timer": "inactive",
                    "mvn-postgres-basebackup.timer": "inactive",
                },
            },
            "invalid active",
        ),
    ],
)
def test_parse_observation_fails_closed(payload, match):
    with pytest.raises(RuntimeError, match=match):
        maintenance.parse_observation("api", _result(payload))


def test_evaluate_window_distinguishes_inactive_and_valid_active():
    inactive = maintenance.evaluate_window(
        [
            maintenance.NodeObservation("api", "absent"),
            maintenance.NodeObservation("reserve", "absent"),
        ]
    )
    active = maintenance.evaluate_window(
        [_active("api"), _active("reserve")],
        now_ns=1_030_000_000_000,
        max_age_seconds=60,
    )

    assert inactive == maintenance.MaintenanceWindow(active=False)
    assert active == maintenance.MaintenanceWindow(
        active=True,
        transaction_id="a" * 32,
        age_seconds=30,
    )


def test_evaluate_window_rejects_partial_mismatched_stale_and_future_markers():
    with pytest.raises(RuntimeError, match="partial"):
        maintenance.evaluate_window(
            [_active("api"), maintenance.NodeObservation("reserve", "absent")]
        )
    with pytest.raises(RuntimeError, match="different"):
        maintenance.evaluate_window(
            [_active("api"), _active("reserve", transaction_id="b" * 32)]
        )
    with pytest.raises(RuntimeError, match="stale"):
        maintenance.evaluate_window(
            [_active("api"), _active("reserve")],
            now_ns=1_061_000_000_000,
            max_age_seconds=60,
        )
    with pytest.raises(RuntimeError, match="future"):
        maintenance.evaluate_window(
            [_active("api", mtime_ns=1_061_000_000_000),
             _active("reserve", mtime_ns=1_061_000_000_000)],
            now_ns=10**12,
            max_age_seconds=60,
        )


def test_detect_window_probes_both_nodes_with_reviewed_source():
    calls = []

    def runner(target, source):
        calls.append((target, source))
        return _result({"status": "absent"})

    window = maintenance.detect_window(
        (("api", "api-target"), ("reserve", "reserve-target")),
        runner=runner,
    )

    assert window.active is False
    assert [target for target, _ in calls] == ["api-target", "reserve-target"]
    assert all(source == maintenance.REMOTE_PROBE for _, source in calls)


def test_remote_probe_contract_checks_marker_generation_and_runtime_fencing():
    source = maintenance.REMOTE_PROBE

    assert 'getattr(os, "O_NOFOLLOW", 0)' in source
    assert '["/usr/bin/systemctl", "is-active", unit]' in source
    assert "before.st_uid != 0" in source
    assert "before.st_gid != 0" in source
    assert "before.st_nlink != 1" in source
    assert "before.st_size != 33" in source
    assert "generation(after) != generation(opened)" in source
    assert 'role_agent_state != "active"' in source
    assert 'state != "inactive"' in source
