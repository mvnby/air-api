from pathlib import Path

import pytest

from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ha.pitr_host_asset_rollout import (
    HostAssetRolloutDependencies,
    rollout_host_assets,
)
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext


TXID = "0123456789abcdef0123456789abcdef"


def _context(tmp_path: Path) -> PinnedSshContext:
    return PinnedSshContext(
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "config",
    )


def _topology(
    *,
    timeline: int = 19,
    primary_alias: str = "mvn-api",
) -> ClusterTopology:
    by_alias = {node.alias: node for node in PATRONI_NODES}
    standby_alias = "zakup" if primary_alias == "mvn-api" else "mvn-api"
    return ClusterTopology(
        primary=by_alias[primary_alias],
        standby=by_alias[standby_alias],
        system_identifier="7657288033494519840",
        timeline=timeline,
    )


def _bundle(node) -> str:
    digest = "a" * 64 if node.alias == "mvn-api" else "b" * 64
    return (
        '{"files":[],"project_dir":"'
        + node.project_dir
        + '","release_sha256":"'
        + digest
        + '","version":1}'
    )


def _unused_runner(args, stdin):
    raise AssertionError((args, stdin))


class FakeOperations:
    def __init__(self):
        self.events = []
        self.states = {"mvn-api": "fresh", "zakup": "fresh"}
        self.topologies = []
        self.default_topology = _topology()
        self.discover_calls = 0
        self.release_failure = None
        self.verify_failure = False

    def discover(self, *, context, runner):
        self.discover_calls += 1
        self.events.append(("topology",))
        if self.topologies:
            return self.topologies.pop(0)
        return self.default_topology

    def bundles(self, nodes):
        return {node.project_dir: _bundle(node) for node in nodes}

    def target_compose(self, nodes, bundles):
        self.events.append(("target-compose", tuple(node.alias for node in nodes)))
        assert set(bundles) == {node.project_dir for node in nodes}
        return "dormant"

    def release(
        self,
        *,
        node,
        context,
        action,
        txid,
        release_bundle,
        runner,
    ):
        self.events.append(("release", action, node.alias, txid))
        if self.release_failure == (action, node.alias):
            raise RuntimeError("simulated release failure")
        if action == "inspect":
            assert release_bundle == _bundle(node)
            return self.states[node.alias]
        if action == "apply":
            assert release_bundle == _bundle(node)
            state = self.states[node.alias]
            result = {
                "fresh": "applied",
                "matching-active": "resumed",
                "matching-finalized": "reopened",
            }[state]
            self.states[node.alias] = "matching-active"
            return result
        assert release_bundle is None
        if action == "finalize":
            already = self.states[node.alias] == "matching-finalized"
            self.states[node.alias] = "matching-finalized"
            return "already-finalized" if already else "finalized"
        raise AssertionError(action)

    def verify(
        self,
        *,
        node,
        context,
        bootstrap_helper,
        phase,
        transaction_id,
        runner,
    ):
        self.events.append(("verify", node.alias, phase, transaction_id))
        if self.verify_failure:
            raise RuntimeError("simulated strict verify failure")

    def dependencies(self):
        return HostAssetRolloutDependencies(
            discover=self.discover,
            bundles=self.bundles,
            release=self.release,
            verify=self.verify,
            target_compose=self.target_compose,
        )


def _operations(events):
    return [event for event in events if event[0] != "topology"]


def test_fresh_rollout_uses_standby_first_and_finishes_with_strict_verify(
    tmp_path,
):
    operations = FakeOperations()

    result = rollout_host_assets(
        context=_context(tmp_path),
        transaction_id=TXID,
        runner=_unused_runner,
        dependencies=operations.dependencies(),
    )

    assert result.primary_alias == "mvn-api"
    assert result.standby_alias == "zakup"
    assert result.timeline == 19
    assert result.compose_profile == "dormant"
    assert result.release_digests == (
        ("zakup", "b" * 64),
        ("mvn-api", "a" * 64),
    )
    assert _operations(operations.events) == [
        ("target-compose", ("zakup", "mvn-api")),
        ("release", "inspect", "zakup", TXID),
        ("release", "inspect", "mvn-api", TXID),
        ("release", "apply", "zakup", TXID),
        ("release", "apply", "mvn-api", TXID),
        ("release", "finalize", "zakup", TXID),
        ("release", "finalize", "mvn-api", TXID),
        ("release", "inspect", "zakup", TXID),
        ("release", "inspect", "mvn-api", TXID),
        ("verify", "mvn-api", "verify", TXID),
    ]


def test_rollout_order_follows_dynamic_patroni_roles_when_zakup_is_primary(
    tmp_path,
):
    operations = FakeOperations()
    operations.default_topology = _topology(primary_alias="zakup")

    result = rollout_host_assets(
        context=_context(tmp_path),
        transaction_id=TXID,
        runner=_unused_runner,
        dependencies=operations.dependencies(),
    )

    assert result.primary_alias == "zakup"
    assert result.standby_alias == "mvn-api"
    apply_events = [
        event
        for event in operations.events
        if event[:2] == ("release", "apply")
    ]
    assert apply_events == [
        ("release", "apply", "mvn-api", TXID),
        ("release", "apply", "zakup", TXID),
    ]
    assert ("verify", "zakup", "verify", TXID) in operations.events


def test_retry_resumes_durable_generations_before_touching_fresh_peer(tmp_path):
    operations = FakeOperations()
    operations.states["zakup"] = "fresh"
    operations.states["mvn-api"] = "matching-active"

    rollout_host_assets(
        context=_context(tmp_path),
        transaction_id=TXID,
        runner=_unused_runner,
        dependencies=operations.dependencies(),
    )

    apply_events = [
        event
        for event in operations.events
        if event[:2] == ("release", "apply")
    ]
    assert apply_events == [
        ("release", "apply", "mvn-api", TXID),
        ("release", "apply", "zakup", TXID),
    ]


def test_fully_finalized_replay_is_idempotent_and_only_verifies(tmp_path):
    operations = FakeOperations()
    operations.states = {
        "mvn-api": "matching-finalized",
        "zakup": "matching-finalized",
    }

    rollout_host_assets(
        context=_context(tmp_path),
        transaction_id=TXID,
        runner=_unused_runner,
        dependencies=operations.dependencies(),
    )

    actions = [
        event[1]
        for event in operations.events
        if event[0] == "release"
    ]
    assert actions == ["inspect", "inspect"]
    assert ("verify", "mvn-api", "verify", TXID) in operations.events


def test_ambiguous_apply_failure_requires_same_transaction_replay(tmp_path):
    operations = FakeOperations()
    operations.release_failure = ("apply", "zakup")

    with pytest.raises(
        RuntimeError,
        match=f"same transaction ID {TXID}",
    ):
        rollout_host_assets(
            context=_context(tmp_path),
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert not any(
        event[:2] == ("release", "finalize")
        for event in operations.events
    )


@pytest.mark.parametrize(
    ("state", "message"),
    (
        ("matching-rolled-back", "durably rolled back"),
        ("preflight-fenced", "full PITR migration preflight"),
    ),
)
def test_incompatible_durable_state_fails_before_mutation(
    tmp_path,
    state,
    message,
):
    operations = FakeOperations()
    operations.states["zakup"] = state

    with pytest.raises(RuntimeError, match=message):
        rollout_host_assets(
            context=_context(tmp_path),
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert not any(
        event[0] == "release" and event[1] in {"apply", "finalize"}
        for event in operations.events
    )


def test_topology_drift_after_first_mutation_fails_closed_for_same_tx(tmp_path):
    operations = FakeOperations()
    # baseline, two guards for each compatibility probe, before first apply,
    # then a changed timeline after the attempted mutation.
    operations.topologies = [
        _topology(),
        _topology(),
        _topology(),
        _topology(),
        _topology(),
        _topology(),
        _topology(timeline=20),
    ]

    with pytest.raises(
        RuntimeError,
        match=f"same transaction ID {TXID}",
    ) as error:
        rollout_host_assets(
            context=_context(tmp_path),
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert "topology drift" in str(error.value)
