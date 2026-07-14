import json
import subprocess
from pathlib import Path

import pytest

from scripts.ha.pitr_cluster_topology import discover_cluster_topology
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext


def _context(tmp_path: Path) -> PinnedSshContext:
    return PinnedSshContext(
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "config",
    )


class TopologyRunner:
    def __init__(self, *, primary: str = "mvn-api", wrong_replica_address: bool = False):
        self.primary = primary
        self.standby = "zakup" if primary == "mvn-api" else "mvn-api"
        self.wrong_replica_address = wrong_replica_address
        self.cluster_override = {}
        self.patroni_override = {}

    def __call__(self, args, stdin):
        node = args[-2]
        command = args[-1]
        if command.endswith("/patroni"):
            payload = {
                "state": "running",
                "role": "leader" if node == self.primary else "replica",
                "patroni": {"name": node, "scope": "mvn-postgres"},
            }
            payload.update(self.patroni_override.get(node, {}))
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
        if command.endswith("/cluster"):
            payload = {
                "members": [
                    {
                        "name": self.primary,
                        "role": "leader",
                        "state": "running",
                        "timeline": 9,
                    },
                    {
                        "name": self.standby,
                        "role": "sync_standby",
                        "state": "streaming",
                        "timeline": 9,
                        "lag": 0,
                    },
                ]
            }
            payload.update(self.cluster_override.get(node, {}))
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
        if "/leader" in command or "/sync" in command:
            return subprocess.CompletedProcess(args, 0, "", "")
        if stdin == "select pg_is_in_recovery();":
            return subprocess.CompletedProcess(
                args, 0, "f\n" if node == self.primary else "t\n", ""
            )
        if stdin == "select system_identifier from pg_control_system();":
            return subprocess.CompletedProcess(args, 0, "7423456789012345678\n", "")
        if stdin and "from pg_stat_replication" in stdin:
            address = "10.66.0.99" if self.wrong_replica_address else {
                "mvn-api": "10.77.0.2",
                "zakup": "10.77.0.1",
            }[self.standby]
            return subprocess.CompletedProcess(
                args,
                0,
                f"{self.standby}|{address}|streaming|sync|0\n",
                "",
            )
        if stdin and "from pg_stat_wal_receiver" in stdin:
            sender = {"mvn-api": "10.77.0.2", "zakup": "10.77.0.1"}[
                self.primary
            ]
            return subprocess.CompletedProcess(
                args, 0, f"streaming|{sender}|slot_{self.standby}|0\n", ""
            )
        if stdin == "show synchronous_standby_names;":
            return subprocess.CompletedProcess(args, 0, f'ANY 1 ("{self.standby}")\n', "")
        raise AssertionError((node, command, stdin))


@pytest.mark.parametrize("primary", ["mvn-api", "zakup"])
def test_strict_topology_is_role_aware_and_needs_no_synthetic_patroni_fields(
    tmp_path, primary
):
    topology = discover_cluster_topology(
        context=_context(tmp_path),
        runner=TopologyRunner(primary=primary),
    )

    assert topology.primary.alias == primary
    assert topology.standby.alias != primary
    assert topology.system_identifier == "7423456789012345678"
    assert topology.timeline == 9


def test_strict_topology_rejects_wrong_replication_source_address(tmp_path):
    with pytest.raises(RuntimeError, match="synchronous replication is not healthy"):
        discover_cluster_topology(
            context=_context(tmp_path),
            runner=TopologyRunner(wrong_replica_address=True),
        )


def test_strict_topology_rejects_nonboolean_patroni_safety_flags(tmp_path):
    runner = TopologyRunner()
    runner.patroni_override["mvn-api"] = {"pending_restart": "false"}
    with pytest.raises(RuntimeError, match="pending_restart state is invalid"):
        discover_cluster_topology(context=_context(tmp_path), runner=runner)


def test_strict_topology_rejects_disagreeing_dcs_views(tmp_path):
    runner = TopologyRunner()
    runner.cluster_override["zakup"] = {
        "members": [
            {
                "name": "mvn-api",
                "role": "leader",
                "state": "running",
                "timeline": 10,
            },
            {
                "name": "zakup",
                "role": "sync_standby",
                "state": "streaming",
                "timeline": 10,
                "lag": 0,
            },
        ]
    }

    with pytest.raises(RuntimeError, match="disagree on the DCS cluster view"):
        discover_cluster_topology(context=_context(tmp_path), runner=runner)


@pytest.mark.parametrize(
    ("extra_member", "message"),
    [
        (
            {
                "name": "zakup",
                "role": "sync_standby",
                "state": "streaming",
                "timeline": 9,
                "lag": 0,
            },
            "member list",
        ),
        (
            {
                "name": "other",
                "role": "replica",
                "state": "streaming",
                "timeline": 9,
                "lag": 0,
            },
            "member list",
        ),
    ],
)
def test_strict_topology_rejects_extra_or_duplicate_members(
    tmp_path, extra_member, message
):
    runner = TopologyRunner()
    members = [
        {
            "name": "mvn-api",
            "role": "leader",
            "state": "running",
            "timeline": 9,
        },
        {
            "name": "zakup",
            "role": "sync_standby",
            "state": "streaming",
            "timeline": 9,
            "lag": 0,
        },
        extra_member,
    ]
    runner.cluster_override["mvn-api"] = {"members": members}
    runner.cluster_override["zakup"] = {"members": members}
    with pytest.raises(RuntimeError, match=message):
        discover_cluster_topology(context=_context(tmp_path), runner=runner)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("lag", True, "lag is invalid"),
        ("pending_restart", "false", "pending restart state is invalid"),
    ],
)
def test_strict_topology_rejects_noncanonical_member_state(
    tmp_path, field, value, message
):
    runner = TopologyRunner()
    members = [
        {
            "name": "mvn-api",
            "role": "leader",
            "state": "running",
            "timeline": 9,
        },
        {
            "name": "zakup",
            "role": "sync_standby",
            "state": "streaming",
            "timeline": 9,
            "lag": 0,
            field: value,
        },
    ]
    runner.cluster_override["mvn-api"] = {"members": members}
    runner.cluster_override["zakup"] = {"members": members}
    with pytest.raises(RuntimeError, match=message):
        discover_cluster_topology(context=_context(tmp_path), runner=runner)
