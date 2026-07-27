from pathlib import Path

import pytest

from scripts.ha.pitr_cluster_migration import (
    MigrationDependencies,
    MigrationResult,
    migrate_cluster,
    validate_transaction_id,
)
from scripts.ha import apply_postgres_pitr_primary_prerequisites as controller
from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext


TXID = "0123456789abcdef0123456789abcdef"
ENV_TEXT = "POSTGRES_PITR_CLUSTER=mvn-api\nsecret=value\n"


def _context(tmp_path: Path) -> PinnedSshContext:
    return PinnedSshContext(
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "config",
    )


def _topology(
    *,
    timeline: int = 9,
    primary_alias: str = "mvn-api",
    system_identifier: str = "7423456789012345678",
) -> ClusterTopology:
    by_alias = {node.alias: node for node in PATRONI_NODES}
    standby_alias = "zakup" if primary_alias == "mvn-api" else "mvn-api"
    return ClusterTopology(
        primary=by_alias[primary_alias],
        standby=by_alias[standby_alias],
        system_identifier=system_identifier,
        timeline=timeline,
    )


def _unused_runner(args, stdin):
    raise AssertionError((args, stdin))


class FakeOperations:
    def __init__(self):
        self.events = []
        self.topologies = []
        self.release_failure = None
        self.secret_failure = None
        self.maintenance_failure = None
        self.fenced_provision_failure = False
        self.role_agent_failure = None
        self.communications_cutover_failure = False
        self.target_compose_failure = False
        self.target_compose_validated = False
        self.role_agent_fail_once = set()
        self.release_results = {}
        self.release_payloads = []
        self.discover_calls = 0
        self.discover_failures = set()

    def discover(self, *, context, runner):
        self.discover_calls += 1
        self.events.append(("topology",))
        if self.discover_calls in self.discover_failures:
            raise RuntimeError("simulated topology failure")
        if self.topologies:
            return self.topologies.pop(0)
        return _topology()

    def bundles(self, nodes):
        return {node.project_dir: f"pinned:{node.alias}" for node in nodes}

    def target_compose(self, nodes, bundles):
        self.target_compose_validated = True
        if self.target_compose_failure:
            raise RuntimeError("simulated target Compose failure")
        assert set(bundles) == {node.project_dir for node in nodes}
        return "dormant"

    def release(self, *, node, context, action, txid, release_bundle, runner):
        event = ("release", action, node.alias, txid)
        self.events.append(event)
        self.release_payloads.append((action, node.alias, release_bundle))
        if action in {"inspect", "apply"}:
            assert release_bundle == f"pinned:{node.alias}"
        else:
            assert release_bundle is None
        if self.release_failure == (action, node.alias):
            raise RuntimeError("simulated release failure")
        return self.release_results.get((action, node.alias), {
            "inspect": "fresh",
            "apply": "applied",
            "rollback": "rolled-back",
            "finalize": "finalized",
        }[action])

    def secret(
        self,
        *,
        node,
        context,
        env_text,
        bootstrap_helper,
        phase,
        transaction_id,
        runner,
    ):
        self.events.append(
            ("secret", phase, node.alias, transaction_id, env_text)
        )
        if self.secret_failure == (phase, node.alias):
            raise RuntimeError("simulated secret phase failure")

    def maintenance(
        self,
        *,
        node,
        context,
        bootstrap_helper,
        phase,
        transaction_id,
        runner,
    ):
        self.events.append(("maintenance", phase, node.alias, transaction_id))
        if self.maintenance_failure == (phase, node.alias):
            raise RuntimeError("simulated maintenance phase failure")

    def role_agent(
        self,
        *,
        node,
        context,
        phase,
        transaction_id,
        runner,
    ):
        self.events.append(("role-agent", phase, node.alias, transaction_id))
        if (phase, node.alias) in self.role_agent_fail_once:
            self.role_agent_fail_once.remove((phase, node.alias))
            raise RuntimeError("simulated one-shot role-agent phase failure")
        if self.role_agent_failure == (phase, node.alias):
            raise RuntimeError("simulated role-agent phase failure")

    def fenced_provision(
        self,
        *,
        node,
        context,
        bootstrap_helper,
        transaction_id,
        runner,
    ):
        self.events.append(("fenced-provision", node.alias, transaction_id))
        if self.fenced_provision_failure:
            raise RuntimeError("simulated fenced provision failure")

    def communications_cutover(
        self,
        *,
        node,
        context,
        transaction_id,
        runner,
    ):
        self.events.append(
            ("communications-cutover", node.alias, transaction_id)
        )
        if self.communications_cutover_failure:
            raise RuntimeError("simulated communications cutover failure")

    def dependencies(self):
        return MigrationDependencies(
            discover=self.discover,
            bundles=self.bundles,
            release=self.release,
            secret=self.secret,
            maintenance=self.maintenance,
            fenced_provision=self.fenced_provision,
            role_agent=self.role_agent,
            communications_cutover=self.communications_cutover,
            target_compose=self.target_compose,
        )


def _mutation_events(events):
    return [event for event in events if event[0] != "topology"]


def test_migration_runs_exact_order_with_topology_around_every_remote_operation(
    tmp_path,
):
    operations = FakeOperations()

    result = migrate_cluster(
        context=_context(tmp_path),
        env_text=ENV_TEXT,
        transaction_id=TXID,
        runner=_unused_runner,
        dependencies=operations.dependencies(),
    )

    assert result.primary_alias == "mvn-api"
    assert result.standby_alias == "zakup"
    assert result.transaction_id == TXID
    assert operations.target_compose_validated is True
    assert _mutation_events(operations.events) == [
        ("release", "inspect", "zakup", TXID),
        ("release", "inspect", "mvn-api", TXID),
        ("communications-cutover", "mvn-api", TXID),
        ("release", "apply", "zakup", TXID),
        ("release", "apply", "mvn-api", TXID),
        ("role-agent", "quiesce-standby", "zakup", TXID),
        ("secret", "preflight", "zakup", TXID, ENV_TEXT),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("secret", "preflight", "mvn-api", TXID, ENV_TEXT),
        ("role-agent", "quiesce-standby", "zakup", TXID),
        ("maintenance", "provision-node", "zakup", TXID),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("role-agent", "quiesce-fenced", "mvn-api", TXID),
        ("fenced-provision", "mvn-api", TXID),
        ("role-agent", "resume-primary", "mvn-api", TXID),
        ("role-agent", "quiesce-standby", "zakup", TXID),
        ("secret", "configure-node", "zakup", TXID, ENV_TEXT),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("secret", "configure-node", "mvn-api", TXID, ENV_TEXT),
        ("role-agent", "quiesce-standby", "zakup", TXID),
        ("maintenance", "scrub-node", "zakup", TXID),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("maintenance", "scrub-node", "mvn-api", TXID),
        ("role-agent", "quiesce-standby", "zakup", TXID),
        ("maintenance", "enable-archive-env", "zakup", TXID),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("maintenance", "enable-archive-env", "mvn-api", TXID),
        ("maintenance", "basebackup", "mvn-api", TXID),
        ("maintenance", "restore-drill", "mvn-api", TXID),
        ("release", "finalize", "zakup", TXID),
        ("release", "finalize", "mvn-api", TXID),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("role-agent", "resume-primary", "mvn-api", TXID),
        ("maintenance", "verify", "mvn-api", TXID),
    ]
    assert len(operations.events) == 1 + 3 * 34
    assert operations.events[0] == ("topology",)
    for index in range(1, len(operations.events), 3):
        assert operations.events[index] == ("topology",)
        assert operations.events[index + 1][0] != "topology"
        assert operations.events[index + 2] == ("topology",)


def test_bundle_apply_failure_preserves_all_journals_for_exact_resume(
    tmp_path,
):
    operations = FakeOperations()
    operations.release_failure = ("apply", "mvn-api")

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    release_events = [event for event in operations.events if event[0] == "release"]
    assert release_events == [
        ("release", "inspect", "zakup", TXID),
        ("release", "inspect", "mvn-api", TXID),
        ("release", "apply", "zakup", TXID),
        ("release", "apply", "mvn-api", TXID),
    ]
    assert len([event for event in operations.events if event[0] == "topology"]) == 11


def test_communications_cutover_failure_blocks_every_bundle_apply(tmp_path):
    operations = FakeOperations()
    operations.communications_cutover_failure = True

    with pytest.raises(
        RuntimeError,
        match=f"resume with the same transaction ID {TXID}",
    ):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event[1] for event in operations.events if event[0] == "release"] == [
        "inspect",
        "inspect",
    ]
    assert (
        "communications-cutover",
        "mvn-api",
        TXID,
    ) in operations.events


def test_first_bundle_digest_rejection_never_authorizes_rollback(tmp_path):
    operations = FakeOperations()
    operations.release_failure = ("apply", "zakup")

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event for event in operations.events if event[0] == "release"] == [
        ("release", "inspect", "zakup", TXID),
        ("release", "inspect", "mvn-api", TXID),
        ("release", "apply", "zakup", TXID),
    ]


def test_primary_preflight_failure_after_standby_window_requires_same_tx_resume(
    tmp_path,
):
    operations = FakeOperations()
    operations.secret_failure = ("preflight", "mvn-api")

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert not any(
        event[0] == "fenced-provision" for event in operations.events
    )
    assert [event[1] for event in operations.events if event[0] == "release"] == [
        "inspect",
        "inspect",
        "apply",
        "apply",
    ]


def test_reopened_finalized_node_forces_roll_forward_before_preflight(tmp_path):
    operations = FakeOperations()
    operations.release_results[("inspect", "zakup")] = "matching-finalized"
    operations.release_results[("apply", "zakup")] = "reopened"
    operations.secret_failure = ("preflight", "mvn-api")

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event[1] for event in operations.events if event[0] == "release"] == [
        "inspect",
        "inspect",
        "apply",
        "apply",
    ]


def test_resumed_active_node_forces_roll_forward_before_preflight(tmp_path):
    operations = FakeOperations()
    operations.release_results[("inspect", "zakup")] = "matching-active"
    operations.release_results[("apply", "zakup")] = "resumed"
    operations.secret_failure = ("preflight", "mvn-api")

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event[1] for event in operations.events if event[0] == "release"] == [
        "inspect",
        "inspect",
        "apply",
        "apply",
    ]


def test_ambiguous_failure_during_first_provision_never_rolls_back(tmp_path):
    operations = FakeOperations()
    operations.maintenance_failure = ("provision-node", "zakup")

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event[1] for event in operations.events if event[0] == "release"] == [
        "inspect",
        "inspect",
        "apply",
        "apply",
    ]
    assert [event[1:3] for event in operations.events if event[0] == "role-agent"][-2:] == [
        ("resume-standby", "zakup"),
        ("resume-primary", "mvn-api"),
    ]


def test_primary_fenced_provision_failure_recovers_agents_for_same_tx(tmp_path):
    operations = FakeOperations()
    operations.fenced_provision_failure = True

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert ("fenced-provision", "mvn-api", TXID) in operations.events
    role_events = [event for event in operations.events if event[0] == "role-agent"]
    assert [event[1:3] for event in role_events[-2:]] == [
        ("resume-standby", "zakup"),
        ("resume-primary", "mvn-api"),
    ]
    assert not any(event[0] == "release" and event[1] == "rollback" for event in operations.events)


def test_quiesce_is_standby_first_and_ambiguous_failure_recovers_both_agents(
    tmp_path,
):
    operations = FakeOperations()
    operations.role_agent_fail_once.add(("quiesce-fenced", "mvn-api"))

    with pytest.raises(
        RuntimeError,
        match="safely fenced, freshly ordered, and restarted",
    ):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    role_events = [event for event in operations.events if event[0] == "role-agent"]
    assert role_events == [
        ("role-agent", "quiesce-standby", "zakup", TXID),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("role-agent", "quiesce-standby", "zakup", TXID),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("role-agent", "quiesce-fenced", "mvn-api", TXID),
        ("role-agent", "quiesce-fenced", "mvn-api", TXID),
        ("role-agent", "quiesce-fenced", "zakup", TXID),
        ("role-agent", "resume-standby", "zakup", TXID),
        ("role-agent", "resume-primary", "mvn-api", TXID),
    ]
    assert not any(
        event[0] == "fenced-provision" for event in operations.events
    )


def test_role_agent_recovery_failure_is_reported_without_rolling_assets_back(
    tmp_path,
):
    operations = FakeOperations()
    operations.maintenance_failure = ("provision-node", "zakup")
    operations.role_agent_failure = ("resume-primary", "mvn-api")

    with pytest.raises(
        RuntimeError,
        match="pinned role-agent safety recovery failed: resume mvn-api",
    ):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event[1] for event in operations.events if event[0] == "release"] == [
        "inspect",
        "inspect",
        "apply",
        "apply",
    ]


def test_recovery_never_resumes_when_either_runtime_fence_is_unproved(tmp_path):
    operations = FakeOperations()
    operations.maintenance_failure = ("provision-node", "zakup")
    operations.role_agent_failure = ("quiesce-fenced", "mvn-api")

    with pytest.raises(RuntimeError, match="did not resume either node"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    recovery = [event for event in operations.events if event[0] == "role-agent"][-2:]
    assert [event[1] for event in recovery] == [
        "quiesce-fenced",
        "quiesce-fenced",
    ]


def test_recovery_keeps_both_nodes_fenced_when_fresh_topology_is_unavailable(
    tmp_path,
):
    operations = FakeOperations()
    operations.maintenance_failure = ("provision-node", "zakup")
    # The compatibility barrier adds two proved read-only operations.
    operations.discover_failures.add(24)

    with pytest.raises(RuntimeError, match="neither node was resumed"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    role_events = [event for event in operations.events if event[0] == "role-agent"]
    assert not any(event[1].startswith("resume-") for event in role_events[-2:])


def test_topology_failure_before_first_agent_quiesce_still_rolls_back_assets(tmp_path):
    operations = FakeOperations()
    operations.topologies = [_topology()] * 11 + [_topology(timeline=10)]

    with pytest.raises(RuntimeError, match="release bundles were rolled back"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert not any(
        event[:2] == ("maintenance", "provision-node")
        for event in operations.events
    )
    assert [event[1] for event in operations.events if event[0] == "release"] == [
        "inspect",
        "inspect",
        "apply",
        "apply",
        "rollback",
        "rollback",
    ]


def test_failure_after_first_successful_configuration_never_rolls_back(tmp_path):
    operations = FakeOperations()
    operations.secret_failure = ("configure-node", "mvn-api")

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    release_actions = [
        event[1] for event in operations.events if event[0] == "release"
    ]
    assert release_actions == ["inspect", "inspect", "apply", "apply"]


def test_ambiguous_failure_during_first_configuration_never_rolls_back(tmp_path):
    operations = FakeOperations()
    operations.secret_failure = ("configure-node", "zakup")

    with pytest.raises(RuntimeError, match=f"resume with the same transaction ID {TXID}"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event[1] for event in operations.events if event[0] == "release"] == [
        "inspect",
        "inspect",
        "apply",
        "apply",
    ]


@pytest.mark.parametrize(
    ("drifted", "field"),
    [
        (_topology(timeline=10), "timeline"),
        (_topology(primary_alias="zakup"), "primary"),
        (_topology(system_identifier="8423456789012345678"), "system_identifier"),
    ],
)
def test_lineage_or_primary_drift_aborts_before_another_mutation(
    tmp_path, drifted, field
):
    operations = FakeOperations()
    operations.topologies = [
        _topology(),
        _topology(),
        drifted,
        drifted,
        drifted,
    ]

    with pytest.raises(RuntimeError, match=field):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event for event in operations.events if event[0] == "release"] == [
        ("release", "inspect", "zakup", TXID)
    ]


def test_same_transaction_id_can_resume_through_idempotent_remote_helpers(tmp_path):
    operations = FakeOperations()

    for _ in range(2):
        result = migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )
        assert result.transaction_id == TXID

    txids = [
        event[3]
        for event in operations.events
        if event[0] in {"release", "secret", "maintenance"}
    ]
    assert txids and set(txids) == {TXID}


@pytest.mark.parametrize(
    "transaction_id",
    ["", "ABCDEF0123456789ABCDEF0123456789", "0" * 31, "g" * 32],
)
def test_transaction_id_is_canonical_lowercase_hex(transaction_id):
    with pytest.raises(RuntimeError, match="32 lowercase hexadecimal"):
        validate_transaction_id(transaction_id)
