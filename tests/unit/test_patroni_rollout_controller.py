from pathlib import Path

import pytest

from scripts.ha.patroni_rollout_schema import (
    LEGACY_ARCHIVE_COMMAND,
    LEGACY_ARCHIVE_COMMAND_SHA256,
    RolloutInputs,
    sha256_text,
)
from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext
from scripts.ha.rollout_patroni_image import (
    RolloutDependencies,
    _Orchestrator,
)


TXID = "0123456789abcdef0123456789abcdef"
DEPLOY_SHA = "1" * 40
CURRENT = "ghcr.io/mvnby/air-api/patroni@sha256:" + "2" * 64
TARGET = "ghcr.io/mvnby/air-api/patroni@sha256:" + "3" * 64
CONTRACTS = {"mvn-api": "4" * 64, "zakup": "5" * 64}


def _inputs(*, resume=False) -> RolloutInputs:
    return RolloutInputs.validated(
        deploy_sha=DEPLOY_SHA,
        publish_run_id="123456",
        publish_run_attempt=1,
        transaction_id=TXID,
        maintenance_transaction_id="f" * 32,
        current_image=CURRENT,
        target_image=TARGET,
        apply=True,
        resume=resume,
    )


def _context(tmp_path: Path) -> PinnedSshContext:
    return PinnedSshContext(
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "config",
    )


def _topology(switched: bool = False) -> ClusterTopology:
    nodes = {node.alias: node for node in PATRONI_NODES}
    return ClusterTopology(
        primary=nodes["zakup" if switched else "mvn-api"],
        standby=nodes["mvn-api" if switched else "zakup"],
        system_identifier="7423456789012345678",
        timeline=10 if switched else 9,
    )


class FakeOperations:
    JOURNAL_ACTIONS = {
        "abort", "apply-archive-command", "finalize", "prove-archive",
        "revert-archive-command", "rollback-node", "switchover", "update-node",
    }

    def __init__(self, *, switched=False, existing=False, baseline_primary="mvn-api"):
        self.switched = switched
        self.baseline_primary = baseline_primary
        self.events = []
        self.statuses = {
            node.alias: {
                "baseline_primary": baseline_primary,
                "baseline_system_identifier": "7423456789012345678",
                "baseline_timeline": 9,
                "completed": [],
                "operation": "idle",
            }
            for node in PATRONI_NODES
        }
        self.fail_action = None
        self.ambiguous_switch = False
        self.fail_discover = False
        self.lose_after_completion = []
        self.prepared = {node.alias for node in PATRONI_NODES} if existing else set()
        standby = "zakup" if baseline_primary == "mvn-api" else "mvn-api"
        self.images = {node.alias: CURRENT for node in PATRONI_NODES}
        if switched:
            self.images[standby] = TARGET

    def _lose_completed_response(self, action, node, extra):
        response = (action, node.alias, (extra or {}).get("record"))
        if response in self.lose_after_completion:
            self.lose_after_completion.remove(response)
            raise RuntimeError("lost SSH response after remote completion")

    def discover(self, **_kwargs):
        if self.fail_discover:
            raise RuntimeError("simulated unavailable standby")
        self.events.append(("topology", "post" if self.switched else "pre"))
        nodes = {node.alias: node for node in PATRONI_NODES}
        standby = "zakup" if self.baseline_primary == "mvn-api" else "mvn-api"
        return ClusterTopology(
            primary=nodes[standby if self.switched else self.baseline_primary],
            standby=nodes[self.baseline_primary if self.switched else standby],
            system_identifier="7423456789012345678",
            timeline=10 if self.switched else 9,
        )

    def remote(self, *, action, node, extra=None, **_kwargs):
        self.events.append((action, node.alias, dict(extra or {})))
        if action == "prepare":
            self.prepared.add(node.alias)
            return "prepared"
        if action == "record":
            record = "record:" + extra["record"]
            if record == "record:switched-over" and self.statuses[node.alias]["operation"] == "switchover":
                self.statuses[node.alias]["operation"] = "idle"
                self.statuses[node.alias]["completed"].append("switchover")
            if record not in self.statuses[node.alias]["completed"]:
                self.statuses[node.alias]["completed"].append(record)
            self._lose_completed_response(action, node, extra)
            return extra["record"]
        if action == "switchover":
            self.switched = True
            if self.ambiguous_switch:
                self.statuses[node.alias]["operation"] = "switchover"
                raise RuntimeError("lost SSH response")
        if action == self.fail_action:
            if action in self.JOURNAL_ACTIONS:
                self.statuses[node.alias]["operation"] = action
            raise RuntimeError("simulated failure")
        if action == "rollback-node" and self.statuses[node.alias]["operation"] == "update-node":
            self.statuses[node.alias]["operation"] = "idle"
            self.statuses[node.alias]["completed"].append("update-node")
        if action == "update-node":
            self.images[node.alias] = TARGET
        if action == "rollback-node":
            self.images[node.alias] = CURRENT
        if action == "attest-target-runtime" and self.images[node.alias] != TARGET:
            raise RuntimeError("runtime is not the target image generation")
        if action == "revert-archive-command" and self.statuses[node.alias]["operation"] == "prove-archive":
            self.statuses[node.alias]["operation"] = "idle"
        if action in self.JOURNAL_ACTIONS:
            self.statuses[node.alias]["operation"] = "idle"
            if action not in self.statuses[node.alias]["completed"]:
                self.statuses[node.alias]["completed"].append(action)
            self._lose_completed_response(action, node, extra)
        return action + "=passed"

    def status(self, *, node, **_kwargs):
        if node.alias not in self.prepared:
            return {"status": "missing"}
        return dict(self.statuses[node.alias])

    def dependencies(self):
        return RolloutDependencies(
            discover=self.discover,
            remote=self.remote,
            status=self.status,
            sleep=lambda _seconds: None,
        )


class LostCompletedActionOperations(FakeOperations):
    def __init__(self, action, *, switched=False, existing=False):
        super().__init__(switched=switched, existing=existing)
        self.lost_action = action
        self.lose_response = True

    def remote(self, *, action, node, extra=None, **kwargs):
        should_lose = (
            self.lose_response
            and action == self.lost_action
            and (action != "prepare" or node.alias == "zakup")
        )
        result = super().remote(action=action, node=node, extra=extra, **kwargs)
        if should_lose:
            self.lose_response = False
            raise RuntimeError(f"lost response after completed {action}")
        return result


def _orchestrator(
    tmp_path: Path, operations: FakeOperations, *, resume=False
) -> _Orchestrator:
    return _Orchestrator(
        context=_context(tmp_path),
        inputs=_inputs(resume=resume),
        contract_digests=CONTRACTS,
        ghcr_username="robot",
        ghcr_token="token",
        runner=lambda *_args: pytest.fail("unexpected subprocess"),
        dependencies=operations.dependencies(),
        helper_digest="6" * 64,
    )


def _mutation_names(events):
    return [event[0] for event in events if event[0] != "topology"]


def _mark_post_switchover(operations):
    records = (
        "record:baseline-primary-mvn-api",
        "record:standby-updated",
        "record:switched-over",
        "record:former-primary-updated",
    )
    for status in operations.statuses.values():
        status["completed"].extend(records)
    operations.images = {node.alias: TARGET for node in PATRONI_NODES}


def test_lost_completed_prepare_on_resume_never_aborts_existing_transaction(tmp_path):
    operations = LostCompletedActionOperations(
        "prepare", switched=True, existing=True
    )
    _mark_post_switchover(operations)

    with pytest.raises(RuntimeError, match="existing transaction remains fenced"):
        _orchestrator(tmp_path, operations, resume=True).run()
    assert "abort" not in _mutation_names(operations.events)

    result = _orchestrator(tmp_path, operations, resume=True).run()
    assert result.final_primary == "zakup"
    assert "abort" not in _mutation_names(operations.events)


def test_lost_completed_stage_after_switchover_rolls_forward_without_abort(tmp_path):
    operations = LostCompletedActionOperations("stage", switched=True, existing=True)
    _mark_post_switchover(operations)

    with pytest.raises(RuntimeError, match="roll-forward state"):
        _orchestrator(tmp_path, operations, resume=True).run()
    assert "abort" not in _mutation_names(operations.events)

    result = _orchestrator(tmp_path, operations, resume=True).run()
    assert result.final_primary == "zakup"
    assert "abort" not in _mutation_names(operations.events)


def test_new_transaction_prepare_failure_still_cleans_prepared_node(tmp_path):
    operations = LostCompletedActionOperations("prepare")

    with pytest.raises(RuntimeError, match="could not prepare both rollout journals"):
        _orchestrator(tmp_path, operations).run()

    abort_nodes = [event[1] for event in operations.events if event[0] == "abort"]
    assert abort_nodes == ["mvn-api"]


@pytest.mark.parametrize(
    ("completed", "operation"),
    [
        (["record:standby-updated"], "idle"),
        (["switchover"], "idle"),
        ([], "switchover"),
        (["record:switched-over"], "idle"),
    ],
)
def test_resume_conservatively_detects_ambiguous_switchover_boundary(
    tmp_path, completed, operation
):
    operations = FakeOperations(existing=True)
    operations.statuses["mvn-api"]["completed"].extend(completed)
    operations.statuses["mvn-api"]["operation"] = operation
    controller = _orchestrator(tmp_path, operations, resume=True)

    assert controller._has_ambiguous_switchover_boundary(operations.statuses)


def test_rollout_orders_both_images_before_archive_command(tmp_path):
    operations = FakeOperations()

    result = _orchestrator(tmp_path, operations).run()

    names = _mutation_names(operations.events)
    standby_update = names.index("update-node")
    switchover = names.index("switchover")
    former_primary_update = names.index("update-node", standby_update + 1)
    dcs_apply = names.index("apply-archive-command")
    archive_proof = names.index("prove-archive")
    assert standby_update < switchover < former_primary_update < dcs_apply < archive_proof
    assert result.original_primary == "mvn-api"
    assert result.final_primary == "zakup"
    assert result.timeline == 10


def test_lost_switchover_response_is_discovered_and_rolls_forward(tmp_path):
    operations = FakeOperations()
    operations.ambiguous_switch = True

    result = _orchestrator(tmp_path, operations).run()

    assert result.final_primary == "zakup"
    assert _mutation_names(operations.events).count("switchover") == 1
    assert "apply-archive-command" in _mutation_names(operations.events)


def test_resume_after_unrecorded_switchover_never_switches_back(tmp_path):
    operations = FakeOperations(switched=True, existing=True)

    result = _orchestrator(tmp_path, operations, resume=True).run()

    assert result.final_primary == "zakup"
    assert "switchover" not in _mutation_names(operations.events)
    assert any(
        event[0] == "record" and event[2].get("record") == "switched-over"
        for event in operations.events
    )


def test_pre_switchover_failure_restores_old_generation_and_unfences(tmp_path):
    operations = FakeOperations()
    operations.fail_action = "update-node"

    with pytest.raises(RuntimeError, match="old image/DCS generation was restored"):
        _orchestrator(tmp_path, operations).run()

    names = _mutation_names(operations.events)
    assert "switchover" not in names
    assert "rollback-node" in names
    assert names.count("abort") == 2


def test_completed_rollback_with_lost_response_is_terminal_across_two_resumes(
    tmp_path,
):
    operations = FakeOperations()
    operations.lose_after_completion = [
        ("record", "zakup", "standby-updated"),
        ("rollback-node", "zakup", None),
    ]

    with pytest.raises(RuntimeError, match="safe rollback could not be proved"):
        _orchestrator(tmp_path, operations).run()

    for status in operations.statuses.values():
        assert "record:standby-updated" in status["completed"]
    assert "rollback-node" in operations.statuses["zakup"]["completed"]
    assert operations.statuses["zakup"]["operation"] == "idle"
    assert "switchover" not in _mutation_names(operations.events)

    with pytest.raises(
        RuntimeError, match="interrupted pre-switchover rollback was reconciled"
    ):
        _orchestrator(tmp_path, operations, resume=True).run()

    assert all(
        "abort" in operations.statuses[node.alias]["completed"]
        for node in PATRONI_NODES
    )
    assert "switchover" not in _mutation_names(operations.events)

    with pytest.raises(RuntimeError, match="aborted .* reconciled"):
        _orchestrator(tmp_path, operations, resume=True).run()

    assert "switchover" not in _mutation_names(operations.events)


def test_stale_standby_record_fences_candidate_on_current_image(tmp_path):
    operations = FakeOperations(existing=True)
    for status in operations.statuses.values():
        status["completed"].append("record:standby-updated")

    with pytest.raises(RuntimeError, match="roll-forward state"):
        _orchestrator(tmp_path, operations, resume=True).run()

    names = _mutation_names(operations.events)
    assert operations.images["zakup"] == CURRENT
    assert "attest-target-runtime" in names
    assert "switchover" not in names
    assert "abort" not in names


def test_archive_proof_failure_compensates_exact_legacy_command(tmp_path):
    operations = FakeOperations()
    operations.fail_action = "prove-archive"

    with pytest.raises(RuntimeError, match="legacy archive_command was restored"):
        _orchestrator(tmp_path, operations).run()

    names = _mutation_names(operations.events)
    assert names.index("apply-archive-command") < names.index("revert-archive-command")
    assert "finalize" not in names


def test_compensated_archive_proof_converges_on_one_resume(tmp_path):
    operations = FakeOperations()
    operations.fail_action = "prove-archive"
    with pytest.raises(RuntimeError, match="legacy archive_command was restored"):
        _orchestrator(tmp_path, operations).run()

    operations.fail_action = None
    result = _orchestrator(tmp_path, operations, resume=True).run()

    assert result.final_primary == "zakup"
    assert _mutation_names(operations.events).count("prove-archive") == 2


@pytest.mark.parametrize(
    ("baseline_primary", "expected_order"),
    [("mvn-api", ["mvn-api", "zakup"]), ("zakup", ["zakup", "mvn-api"])],
)
def test_partial_finalize_resume_proves_and_unfences_primary_last(
    tmp_path, baseline_primary, expected_order
):
    operations = FakeOperations(
        switched=True, existing=True, baseline_primary=baseline_primary
    )
    for status in operations.statuses.values():
        status["completed"].append("record:final-proved")
    operations.statuses[expected_order[0]]["completed"].append("finalize")

    result = _orchestrator(tmp_path, operations, resume=True).run()

    finalize_nodes = [event[1] for event in operations.events if event[0] == "finalize"]
    assert finalize_nodes == expected_order
    assert result.final_primary == expected_order[-1]
    assert "preflight" not in _mutation_names(operations.events)


def test_both_finalized_resume_is_idempotent_without_recreating_markers(tmp_path):
    operations = FakeOperations(switched=True, existing=True)
    for status in operations.statuses.values():
        status["completed"].extend(["record:final-proved", "finalize"])

    result = _orchestrator(tmp_path, operations, resume=True).run()

    assert result.final_primary == "zakup"
    assert [event[1] for event in operations.events if event[0] == "finalize"] == [
        "mvn-api", "zakup"
    ]
    assert not any(event[0] == "prepare" for event in operations.events)


def test_partial_abort_resume_finishes_terminal_abort_on_both_nodes(tmp_path):
    operations = FakeOperations(existing=True)
    operations.statuses["mvn-api"]["completed"].append("abort")

    with pytest.raises(RuntimeError, match="aborted .* reconciled"):
        _orchestrator(tmp_path, operations, resume=True).run()

    abort_nodes = [event[1] for event in operations.events if event[0] == "abort"]
    assert abort_nodes[-2:] == ["zakup", "mvn-api"]
    assert "preflight" not in _mutation_names(operations.events)


def test_resume_repairs_interrupted_update_before_strict_topology_discovery(tmp_path):
    operations = FakeOperations(existing=True)
    operations.statuses["zakup"]["operation"] = "update-node"
    operations.fail_discover = True

    with pytest.raises(RuntimeError, match="interrupted pre-switchover update was rolled back"):
        _orchestrator(tmp_path, operations, resume=True).run()

    assert "rollback-node" in _mutation_names(operations.events)
    assert not any(event[0] == "topology" for event in operations.events)


def test_final_quorum_proof_precedes_shared_final_record_and_unfencing(tmp_path):
    operations = FakeOperations()
    _orchestrator(tmp_path, operations).run()
    events = operations.events
    final_record = max(
        index for index, event in enumerate(events)
        if event[0] == "record" and event[2].get("record") == "final-proved"
    )
    final_quorum = max(
        index for index, event in enumerate(events[:final_record])
        if event[0] == "prove-etcd"
    )
    first_finalize = min(index for index, event in enumerate(events) if event[0] == "finalize")
    assert final_quorum < final_record < first_finalize


def test_inputs_and_compiled_legacy_command_are_fail_closed():
    assert sha256_text(LEGACY_ARCHIVE_COMMAND) == LEGACY_ARCHIVE_COMMAND_SHA256
    with pytest.raises(RuntimeError, match="publish run attempt"):
        RolloutInputs.validated(
            deploy_sha=DEPLOY_SHA,
            publish_run_id="123456",
            publish_run_attempt=0,
            transaction_id=TXID,
            maintenance_transaction_id="f" * 32,
            current_image=CURRENT,
            target_image=TARGET,
            apply=True,
        )
    with pytest.raises(RuntimeError, match="apply=true"):
        RolloutInputs.validated(
            deploy_sha=DEPLOY_SHA,
            publish_run_id="123456",
            publish_run_attempt=1,
            transaction_id=TXID,
            maintenance_transaction_id="f" * 32,
            current_image=CURRENT,
            target_image=TARGET,
            apply=False,
        )
    with pytest.raises(RuntimeError, match="immutable reviewed digest"):
        RolloutInputs.validated(
            deploy_sha=DEPLOY_SHA,
            publish_run_id="123456",
            publish_run_attempt=1,
            transaction_id=TXID,
            maintenance_transaction_id="f" * 32,
            current_image="ghcr.io/other/image@sha256:" + "2" * 64,
            target_image=TARGET,
            apply=True,
        )
