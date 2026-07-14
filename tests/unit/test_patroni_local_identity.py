import json
import subprocess
import time
import urllib.error
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_local_identity


@pytest.mark.parametrize(
    ("role", "active_state", "enabled_state", "expected"),
    [
        ("primary", "active", "enabled", True),
        ("primary", "activating", "enabled", False),
        ("standby", "inactive", "disabled", True),
        ("standby", "deactivating", "disabled", False),
    ],
)
def test_systemd_match_requires_exact_inactive_or_active_state(
    monkeypatch, role, active_state, enabled_state, expected
):
    config = SimpleNamespace(primary_systemd_units=("wal.timer",))

    def run(args, **_kwargs):
        if args[1:4] == ["show", "--property=ActiveState", "--value"]:
            return subprocess.CompletedProcess(args, 0, active_state + "\n", "")
        if args[1:2] == ["is-enabled"]:
            code = 0 if enabled_state == "enabled" else 1
            return subprocess.CompletedProcess(args, code, enabled_state + "\n", "")
        raise AssertionError(args)

    monkeypatch.setattr(patroni_local_identity.subprocess, "run", run)

    assert patroni_local_identity.systemd_units_match(config, role) is expected


def test_systemd_query_timeout_is_not_treated_as_inactive(monkeypatch):
    config = SimpleNamespace(primary_systemd_units=("wal.timer",))

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("systemctl", 10)

    monkeypatch.setattr(patroni_local_identity.subprocess, "run", timeout)

    assert patroni_local_identity.systemd_units_match(config, "standby") is False


class _PatroniResponse:
    def __init__(self, payload: dict[str, object]):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


def _patroni_payload(role: str, *, name: str = "mvn-api") -> dict[str, object]:
    return {
        "state": "running",
        "role": role,
        "timeline": 7,
        "database_system_identifier": "7657288033494519840",
        "dcs_last_seen": time.time(),
        "patroni": {"name": name, "scope": "mvn-postgres"},
    }


def _cluster_payload(*, leader: str = "mvn-api", timeline: int = 7):
    return {
        "members": [
            {"name": leader, "role": "leader", "state": "running", "timeline": timeline},
            {
                "name": "zakup" if leader == "mvn-api" else "mvn-api",
                "role": "sync_standby",
                "state": "streaming",
                "timeline": timeline,
            },
        ]
    }


def _mock_patroni(monkeypatch, *, status, leader=None, cluster=None) -> list[str]:
    urls: list[str] = []

    def urlopen(url, **_kwargs):
        urls.append(url)
        if url.endswith("/patroni"):
            return _PatroniResponse(status)
        if url.endswith("/leader") and leader is not None:
            return _PatroniResponse(leader)
        if url.endswith("/cluster") and cluster is not None:
            return _PatroniResponse(cluster)
        raise urllib.error.URLError(f"unavailable endpoint: {url}")

    monkeypatch.setattr(patroni_local_identity.urllib.request, "urlopen", urlopen)
    return urls


def _fetch() -> str:
    return patroni_local_identity.fetch_patroni_role(
        "http://127.0.0.1:8008/patroni",
        expected_name="mvn-api",
        expected_scope="mvn-postgres",
        max_dcs_age_seconds=20,
    )


@pytest.mark.parametrize(
    ("reported_role", "expected_role"),
    [("leader", "primary"), ("primary", "primary"), ("replica", "standby")],
)
def test_fetch_role_requires_strict_identity_and_leader_lock(
    monkeypatch, reported_role, expected_role
):
    status = _patroni_payload(reported_role)
    urls = _mock_patroni(
        monkeypatch, status=status, leader=dict(status), cluster=_cluster_payload()
    )

    assert _fetch() == expected_role
    assert urls == (
        ["http://127.0.0.1:8008/patroni"]
        if expected_role == "standby"
        else [
            "http://127.0.0.1:8008/patroni",
            "http://127.0.0.1:8008/leader",
            "http://127.0.0.1:8008/cluster",
        ]
    )


def test_fetch_role_rejects_unknown_running_role(monkeypatch):
    _mock_patroni(monkeypatch, status=_patroni_payload("mystery"))
    with pytest.raises(ValueError, match="unsupported Patroni role: mystery"):
        _fetch()


@pytest.mark.parametrize(
    ("unsafe_flag", "unsafe_value"),
    [
        ("pending_restart", True),
        ("pause", True),
        ("cluster_unlocked", True),
        ("failsafe_mode_is_active", True),
        ("cluster_unlocked", "true"),
    ],
)
def test_fetch_role_rejects_unsafe_patroni_state(
    monkeypatch, unsafe_flag, unsafe_value
):
    status = _patroni_payload("leader")
    status[unsafe_flag] = unsafe_value
    _mock_patroni(monkeypatch, status=status)
    with pytest.raises(ValueError, match="Patroni reports"):
        _fetch()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload["patroni"].update(name="other"), "Patroni name"),
        (lambda payload: payload["patroni"].update(scope="other"), "Patroni scope"),
        (
            lambda payload: payload.update(dcs_last_seen=time.time() - 3600),
            "DCS observation is stale",
        ),
    ],
)
def test_fetch_role_rejects_wrong_identity_or_stale_dcs(
    monkeypatch, mutation, message
):
    status = _patroni_payload("leader")
    mutation(status)
    _mock_patroni(monkeypatch, status=status)
    with pytest.raises(ValueError, match=message):
        _fetch()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("leader_unavailable", "unavailable endpoint"),
        ("leader_role", "did not return the local primary"),
        ("leader_system_id", "database_system_identifier"),
        ("dcs_leader", "leader identity is not the local node"),
        ("dcs_timeline", "timeline disagrees"),
        ("two_leaders", "reports 2 DCS leaders"),
    ],
)
def test_primary_requires_coherent_leader_endpoint_and_dcs_view(
    monkeypatch, case, message
):
    status = _patroni_payload("leader")
    leader = dict(status)
    cluster = _cluster_payload()
    if case == "leader_unavailable":
        leader = None
    elif case == "leader_role":
        leader["role"] = "replica"
    elif case == "leader_system_id":
        leader["database_system_identifier"] = "other"
    elif case == "dcs_leader":
        cluster = _cluster_payload(leader="zakup")
    elif case == "dcs_timeline":
        cluster = _cluster_payload(timeline=6)
    elif case == "two_leaders":
        cluster["members"][1]["role"] = "leader"
    _mock_patroni(monkeypatch, status=status, leader=leader, cluster=cluster)
    with pytest.raises((ValueError, urllib.error.URLError), match=message):
        _fetch()


def _root_metadata(real_stat, **overrides):
    values = {
        "st_dev": real_stat.st_dev,
        "st_ino": real_stat.st_ino,
        "st_mode": real_stat.st_mode,
        "st_uid": 0,
        "st_gid": 0,
        "st_nlink": 1,
        "st_size": real_stat.st_size,
        "st_mtime_ns": real_stat.st_mtime_ns,
        "st_ctime_ns": real_stat.st_ctime_ns,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_maintenance_marker_requires_exact_root_owned_0600_transaction_file(
    tmp_path, monkeypatch
):
    marker = tmp_path / "maintenance"
    transaction_id = "a" * 32
    marker.write_text(transaction_id + "\n", encoding="ascii")
    marker.chmod(0o600)
    real_fstat = patroni_local_identity.os.fstat
    opened_flags: list[int] = []
    real_open = patroni_local_identity.os.open

    def safe_open(path, flags):
        opened_flags.append(flags)
        return real_open(path, flags)

    monkeypatch.setattr(patroni_local_identity, "MAINTENANCE_MARKER_PATH", marker)
    monkeypatch.setattr(patroni_local_identity.os, "open", safe_open)
    monkeypatch.setattr(
        patroni_local_identity.os,
        "fstat",
        lambda descriptor: _root_metadata(real_fstat(descriptor)),
    )

    assert patroni_local_identity.read_maintenance_transaction_id() == transaction_id
    assert opened_flags[0] & getattr(patroni_local_identity.os, "O_NOFOLLOW", 0)


@pytest.mark.parametrize(
    ("metadata", "content"),
    [
        ({"st_uid": 1000}, "a" * 32 + "\n"),
        ({"st_gid": 1000}, "a" * 32 + "\n"),
        ({"st_mode": 0o100644}, "a" * 32 + "\n"),
        ({"st_nlink": 2}, "a" * 32 + "\n"),
        ({}, "A" * 32 + "\n"),
        ({}, "a" * 31 + "x\n"),
    ],
)
def test_maintenance_marker_rejects_unsafe_metadata_or_content(
    tmp_path, monkeypatch, metadata, content
):
    marker = tmp_path / "maintenance"
    marker.write_text(content, encoding="ascii")
    marker.chmod(0o600)
    real_fstat = patroni_local_identity.os.fstat
    monkeypatch.setattr(patroni_local_identity, "MAINTENANCE_MARKER_PATH", marker)
    monkeypatch.setattr(
        patroni_local_identity.os,
        "fstat",
        lambda descriptor: _root_metadata(real_fstat(descriptor), **metadata),
    )
    with pytest.raises(RuntimeError, match="maintenance marker"):
        patroni_local_identity.read_maintenance_transaction_id()


def test_maintenance_marker_rejects_symlink(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.write_text("a" * 32 + "\n", encoding="ascii")
    marker = tmp_path / "maintenance"
    marker.symlink_to(target)
    monkeypatch.setattr(patroni_local_identity, "MAINTENANCE_MARKER_PATH", marker)
    with pytest.raises(RuntimeError, match="unsafe PITR maintenance marker"):
        patroni_local_identity.read_maintenance_transaction_id()
