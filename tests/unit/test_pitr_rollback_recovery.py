import json
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.ha import pitr_remote_execution
from scripts.ha.pitr_cluster_migration import migrate_cluster
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES
from tests.unit.test_pitr_bundle_transport import (
    TXID,
    _context,
    _payload,
    _remote_namespace,
    _write,
)
from tests.unit.test_pitr_cluster_migration import (
    ENV_TEXT,
    FakeOperations,
    _unused_runner,
)


NEW_TXID = "2" * 32


def _seed_preflight(namespace, project, *, marker=True, txid=TXID):
    marker_path = Path(namespace["MAINTENANCE_MARKER"])
    if marker:
        _write(marker_path, (txid + "\n").encode("ascii"), 0o600)
    receipt = project / ".ha-communications-cutover-preflight"
    _write(
        receipt,
        f"communications-off-drained-v1\n{txid}\n".encode("ascii"),
        0o600,
    )
    fence = project / ".ha-communications-worker-release-fenced"
    _write(fence, b"fenced\n", 0o600)
    return marker_path, receipt, fence


def _release_store(tmp_path):
    tmp_path.mkdir()
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, value = _payload(namespace, project, compose, tool)
    return namespace, project, compose, tool, payload, value


def _snapshot_files(*paths):
    snapshots = {}
    for path in paths:
        path = Path(path)
        try:
            metadata = path.stat()
        except FileNotFoundError:
            snapshots[str(path)] = None
        else:
            snapshots[str(path)] = (
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_mtime_ns,
                path.read_bytes(),
            )
    return snapshots


def _release_state_paths(namespace, project, compose, tool, txid):
    return (
        compose,
        tool,
        Path(namespace["RELEASE_MANIFEST"]),
        Path(namespace["MAINTENANCE_MARKER"]),
        project / ".ha-communications-cutover-preflight",
        project / ".ha-communications-worker-release-fenced",
        Path(namespace["ROLLBACK_RECEIPT_ROOT"]) / f"{txid}.json",
        Path(namespace["TRANSACTION_ROOT"]) / txid / "journal.json",
    )


def _seed_conflicting_preflight(namespace, project, *, kind, txid):
    owner = TXID if kind == "foreign" else txid
    _marker, receipt, fence = _seed_preflight(
        namespace, project, marker=False, txid=owner
    )
    if kind == "missing-fence":
        fence.unlink()
    elif kind == "invalid-fence":
        _write(fence, b"not-fenced\n", 0o600)
    return receipt, fence


def test_matching_rolled_back_requires_exact_release_contract_and_old_generations(
    tmp_path,
):
    namespace, project, compose, tool, payload, _ = _release_store(tmp_path / "node")
    assert namespace["execute"](
        "apply", TXID, str(project), compose.name, payload
    ) == "applied"
    assert namespace["execute"](
        "rollback", TXID, str(project), compose.name, b""
    ) == "rolled-back"
    assert namespace["execute"](
        "inspect", TXID, str(project), compose.name, payload
    ) == "matching-rolled-back"

    changed, _ = _payload(
        namespace,
        project,
        compose,
        tool,
        compose_content=b"another-release",
    )
    with pytest.raises(RuntimeError, match="belongs to another release"):
        namespace["execute"](
            "inspect", TXID, str(project), compose.name, changed
        )

    _write(compose, b"tampered-old-generation", 0o644)
    with pytest.raises(RuntimeError, match="does not match"):
        namespace["execute"](
            "inspect", TXID, str(project), compose.name, payload
        )
    _write(compose, b"old-compose", 0o644)

    receipt_path = Path(namespace["ROLLBACK_RECEIPT_ROOT"]) / f"{TXID}.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["old_generations"][0]["mode"] = 0o600
    _write(receipt_path, namespace["canonical"](receipt) + b"\n", 0o600)
    with pytest.raises(RuntimeError, match="generation is invalid"):
        namespace["execute"](
            "inspect", TXID, str(project), compose.name, payload
        )


def test_same_node_finalized_and_rolled_back_state_is_rejected(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"new-compose", 0o644)
    _write(tool, b"new-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    assert namespace["execute"](
        "apply", TXID, str(project), compose.name, payload
    ) == "applied"
    txdir = Path(namespace["TRANSACTION_ROOT"]) / TXID
    journal = json.loads((txdir / "journal.json").read_text())
    manifest = namespace["release_manifest"](journal)
    assert namespace["execute"](
        "rollback", TXID, str(project), compose.name, b""
    ) == "rolled-back"
    _write(
        Path(namespace["RELEASE_MANIFEST"]),
        namespace["canonical"](manifest) + b"\n",
        0o600,
    )

    state_paths = _release_state_paths(
        namespace, project, compose, tool, TXID
    )
    before = _snapshot_files(*state_paths)
    cases = [
        ("inspect", payload, "both finalized and rolled back"),
        ("apply", payload, "already has a rollback receipt"),
        ("finalize", b"", "already has a rollback receipt"),
        ("rollback", b"", "cannot roll back a finalized"),
    ]
    for action, action_payload, error in cases:
        with pytest.raises(RuntimeError, match=error):
            namespace["execute"](
                action, TXID, str(project), compose.name, action_payload
            )
        assert _snapshot_files(*state_paths) == before


@pytest.mark.parametrize("receipt_only", [False, True])
def test_preflight_only_state_is_inspectable_and_has_distinct_rollback_result(
    tmp_path, receipt_only
):
    namespace, project, compose, tool, payload, _ = _release_store(tmp_path / "node")
    marker, receipt, fence = _seed_preflight(namespace, project)
    if receipt_only:
        marker.unlink()

    assert namespace["execute"](
        "inspect", TXID, str(project), compose.name, payload
    ) == "preflight-fenced"
    assert namespace["execute"](
        "rollback", TXID, str(project), compose.name, b""
    ) == "preflight-rolled-back"

    assert not marker.exists()
    assert not receipt.exists()
    assert fence.read_bytes() == b"fenced\n"
    assert stat.S_IMODE(fence.stat().st_mode) == 0o600


def test_preflight_cleanup_crash_replays_marker_first_with_both_directory_fsyncs(
    tmp_path,
):
    namespace, project, compose, _tool, payload, _ = _release_store(tmp_path / "node")
    marker, receipt, fence = _seed_preflight(namespace, project)
    fsync_paths = []
    real_fsync = namespace["fsync_dir"]
    real_remove_receipt = namespace["remove_communications_cutover_receipt"]

    def recording_fsync(path):
        fsync_paths.append(path)
        real_fsync(path)

    def crash_after_marker(project_dir, txid):
        assert project_dir == str(project)
        assert txid == TXID
        assert not marker.exists()
        assert receipt.exists()
        raise RuntimeError("injected preflight cleanup crash")

    namespace["fsync_dir"] = recording_fsync
    namespace["remove_communications_cutover_receipt"] = crash_after_marker
    with pytest.raises(RuntimeError, match="injected preflight cleanup crash"):
        namespace["execute"](
            "rollback", TXID, str(project), compose.name, b""
        )

    assert not marker.exists()
    assert receipt.exists()
    assert namespace["execute"](
        "inspect", TXID, str(project), compose.name, payload
    ) == "preflight-fenced"
    namespace["remove_communications_cutover_receipt"] = real_remove_receipt
    assert namespace["execute"](
        "rollback", TXID, str(project), compose.name, b""
    ) == "preflight-rolled-back"

    assert fsync_paths[-2:] == [str(marker.parent), str(project)]
    assert not receipt.exists()
    assert fence.read_bytes() == b"fenced\n"


class _ExecutorOperations(FakeOperations):
    def __init__(self, stores):
        super().__init__()
        self.stores = stores

    def bundles(self, nodes):
        return {
            node.project_dir: self.stores[node.alias]["payload"]
            for node in nodes
        }

    def release(self, *, node, context, action, txid, release_bundle, runner):
        self.events.append(("release", action, node.alias, txid))
        store = self.stores[node.alias]
        return store["namespace"]["execute"](
            action,
            txid,
            str(store["project"]),
            store["compose"].name,
            release_bundle if action in {"inspect", "apply"} else b"",
        )


def test_controller_e2e_cleans_receipt_only_peer_and_requires_new_txid(tmp_path):
    by_alias = {node.alias: node for node in PATRONI_NODES}
    stores = {}
    for alias in by_alias:
        namespace, project, compose, tool, payload, _ = _release_store(
            tmp_path / alias
        )
        stores[alias] = {
            "namespace": namespace,
            "project": project,
            "compose": compose,
            "tool": tool,
            "payload": payload,
        }

    standby = stores["zakup"]
    assert standby["namespace"]["execute"](
        "apply",
        TXID,
        str(standby["project"]),
        standby["compose"].name,
        standby["payload"],
    ) == "applied"
    assert standby["namespace"]["execute"](
        "rollback",
        TXID,
        str(standby["project"]),
        standby["compose"].name,
        b"",
    ) == "rolled-back"
    primary = stores["mvn-api"]
    marker, receipt, fence = _seed_preflight(
        primary["namespace"], primary["project"]
    )
    marker.unlink()

    operations = _ExecutorOperations(stores)
    with pytest.raises(RuntimeError, match="new transaction ID"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert [event[1:3] for event in operations.events if event[0] == "release"] == [
        ("inspect", "zakup"),
        ("inspect", "mvn-api"),
        ("rollback", "mvn-api"),
        ("rollback", "zakup"),
    ]
    assert not receipt.exists()
    assert fence.read_bytes() == b"fenced\n"
    for store in stores.values():
        assert store["namespace"]["execute"](
            "inspect",
            NEW_TXID,
            str(store["project"]),
            store["compose"].name,
            store["payload"],
        ) == "fresh"


def test_role_flipped_foreign_receipt_blocks_new_tx_before_any_apply_or_finalize(
    tmp_path,
):
    stores = {}
    for node in PATRONI_NODES:
        namespace, project, compose, tool, payload, _ = _release_store(
            tmp_path / node.alias
        )
        stores[node.alias] = {
            "namespace": namespace,
            "project": project,
            "compose": compose,
            "tool": tool,
            "payload": payload,
        }
    former_primary = stores["zakup"]
    marker, receipt, fence = _seed_preflight(
        former_primary["namespace"],
        former_primary["project"],
        marker=False,
    )
    assert not marker.exists()
    assert receipt.exists()
    assert fence.exists()

    operations = _ExecutorOperations(stores)
    with pytest.raises(RuntimeError, match="belongs to another transaction"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=NEW_TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    release_events = [
        event for event in operations.events if event[0] == "release"
    ]
    assert release_events == [
        ("release", "inspect", "zakup", NEW_TXID),
    ]
    assert not any(
        event[1] in {"apply", "finalize"} for event in release_events
    )
    assert not any(
        event[0] == "communications-cutover" for event in operations.events
    )
    for store in stores.values():
        assert not (
            Path(store["namespace"]["TRANSACTION_ROOT"]) / NEW_TXID
        ).exists()


@pytest.mark.parametrize(
    ("artifact_kind", "error"),
    [
        ("foreign", "belongs to another transaction"),
        ("missing-fence", "missing its release fence"),
        ("invalid-fence", "release fence is invalid"),
    ],
)
def test_apply_barrier_rejects_conflict_without_state_mutation(
    tmp_path, artifact_kind, error
):
    namespace, project, compose, tool, payload, _ = _release_store(
        tmp_path / "node"
    )
    _seed_conflicting_preflight(
        namespace,
        project,
        kind=artifact_kind,
        txid=NEW_TXID,
    )
    state_paths = _release_state_paths(
        namespace, project, compose, tool, NEW_TXID
    )
    before = _snapshot_files(*state_paths)

    with pytest.raises(RuntimeError, match=error):
        namespace["execute"](
            "apply", NEW_TXID, str(project), compose.name, payload
        )

    assert _snapshot_files(*state_paths) == before
    assert not Path(namespace["STATE_ROOT"]).exists()


@pytest.mark.parametrize(
    "marker_owner",
    [
        NEW_TXID,
        TXID,
    ],
)
def test_marker_only_state_cannot_bypass_inspect_or_mutation_barrier(
    tmp_path, marker_owner
):
    namespace, project, compose, tool, payload, _ = _release_store(
        tmp_path / "node"
    )
    marker = Path(namespace["MAINTENANCE_MARKER"])
    _write(marker, (marker_owner + "\n").encode("ascii"), 0o600)
    state_paths = _release_state_paths(
        namespace, project, compose, tool, NEW_TXID
    )
    before = _snapshot_files(*state_paths)

    actions = [("inspect", payload), ("apply", payload)]
    if marker_owner != NEW_TXID:
        actions.extend([("rollback", b""), ("finalize", b"")])
    for action, action_payload in actions:
        with pytest.raises(
            RuntimeError,
            match="maintenance marker|another release transaction owns",
        ):
            namespace["execute"](
                action,
                NEW_TXID,
                str(project),
                compose.name,
                action_payload,
            )
        assert _snapshot_files(*state_paths) == before
        assert not Path(namespace["STATE_ROOT"]).exists()


def test_active_state_missing_marker_is_rejected_before_every_action_mutation(
    tmp_path,
):
    namespace, project, compose, tool, payload, _ = _release_store(
        tmp_path / "node"
    )
    assert namespace["execute"](
        "apply", NEW_TXID, str(project), compose.name, payload
    ) == "applied"
    marker = Path(namespace["MAINTENANCE_MARKER"])
    marker.unlink()
    state_paths = _release_state_paths(
        namespace, project, compose, tool, NEW_TXID
    )
    before = _snapshot_files(*state_paths)

    for action, action_payload in [
        ("inspect", payload),
        ("apply", payload),
        ("rollback", b""),
        ("finalize", b""),
    ]:
        with pytest.raises(RuntimeError, match="missing its exact marker"):
            namespace["execute"](
                action,
                NEW_TXID,
                str(project),
                compose.name,
                action_payload,
            )
        assert _snapshot_files(*state_paths) == before


@pytest.mark.parametrize("release_state", ["active", "rolled-back"])
def test_foreign_receipt_is_not_masked_by_active_or_rolled_back_state(
    tmp_path, release_state
):
    namespace, project, compose, tool, payload, _ = _release_store(
        tmp_path / "node"
    )
    assert namespace["execute"](
        "apply", NEW_TXID, str(project), compose.name, payload
    ) == "applied"
    if release_state == "rolled-back":
        assert namespace["execute"](
            "rollback", NEW_TXID, str(project), compose.name, b""
        ) == "rolled-back"
    _seed_conflicting_preflight(
        namespace, project, kind="foreign", txid=NEW_TXID
    )
    state_paths = _release_state_paths(
        namespace, project, compose, tool, NEW_TXID
    )
    before = _snapshot_files(*state_paths)

    for action, action_payload in [
        ("inspect", payload),
        ("apply", payload),
        ("rollback", b""),
    ]:
        with pytest.raises(RuntimeError, match="belongs to another transaction"):
            namespace["execute"](
                action,
                NEW_TXID,
                str(project),
                compose.name,
                action_payload,
            )
        assert _snapshot_files(*state_paths) == before


@pytest.mark.parametrize(
    ("artifact_kind", "error"),
    [
        ("foreign", "belongs to another transaction"),
        ("missing-fence", "missing its release fence"),
        ("invalid-fence", "release fence is invalid"),
    ],
)
def test_finalized_state_cannot_mask_conflict_or_mutate_manifest_on_replay(
    tmp_path, artifact_kind, error
):
    namespace, project, compose, tool, payload, _ = _release_store(
        tmp_path / "node"
    )
    assert namespace["execute"](
        "apply", NEW_TXID, str(project), compose.name, payload
    ) == "applied"
    assert namespace["execute"](
        "finalize", NEW_TXID, str(project), compose.name, b""
    ) == "finalized"
    _seed_conflicting_preflight(
        namespace,
        project,
        kind=artifact_kind,
        txid=NEW_TXID,
    )
    state_paths = _release_state_paths(
        namespace, project, compose, tool, NEW_TXID
    )
    before = _snapshot_files(*state_paths)

    for action, action_payload in [("inspect", payload), ("finalize", b"")]:
        with pytest.raises(RuntimeError, match=error):
            namespace["execute"](
                action,
                NEW_TXID,
                str(project),
                compose.name,
                action_payload,
            )
        assert _snapshot_files(*state_paths) == before


def test_controller_rolls_back_active_peer_and_skips_fresh_peer(tmp_path):
    for peer_state, expected_cleanup in [
        ("matching-active", ["mvn-api", "zakup"]),
        ("fresh", ["zakup"]),
    ]:
        operations = FakeOperations()
        operations.release_results[("inspect", "zakup")] = "matching-rolled-back"
        operations.release_results[("inspect", "mvn-api")] = peer_state

        with pytest.raises(RuntimeError, match="new transaction ID"):
            migrate_cluster(
                context=_context(tmp_path),
                env_text=ENV_TEXT,
                transaction_id=TXID,
                runner=_unused_runner,
                dependencies=operations.dependencies(),
            )

        assert [
            event[2]
            for event in operations.events
            if event[:2] == ("release", "rollback")
        ] == expected_cleanup
        assert not any(
            event[0] == "communications-cutover" for event in operations.events
        )


def test_controller_rejects_rolled_back_and_finalized_mix_without_cleanup(tmp_path):
    operations = FakeOperations()
    operations.release_results[("inspect", "zakup")] = "matching-rolled-back"
    operations.release_results[("inspect", "mvn-api")] = "matching-finalized"

    with pytest.raises(RuntimeError, match="conflicts with a finalized peer"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    assert not any(
        event[:2] == ("release", "rollback") for event in operations.events
    )
    assert not any(
        event[0] == "communications-cutover" for event in operations.events
    )


def test_controller_replays_interrupted_cleanup_with_same_tx_then_stops(tmp_path):
    operations = FakeOperations()
    operations.release_results[("inspect", "zakup")] = "matching-rolled-back"
    operations.release_results[("inspect", "mvn-api")] = "preflight-fenced"
    operations.release_failure = ("rollback", "mvn-api")

    with pytest.raises(RuntimeError, match="retry with the same transaction ID"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    operations.release_failure = None
    with pytest.raises(RuntimeError, match="new transaction ID"):
        migrate_cluster(
            context=_context(tmp_path),
            env_text=ENV_TEXT,
            transaction_id=TXID,
            runner=_unused_runner,
            dependencies=operations.dependencies(),
        )

    rollbacks = [
        event[2]
        for event in operations.events
        if event[:2] == ("release", "rollback")
    ]
    assert rollbacks == ["mvn-api", "mvn-api", "zakup"]


@pytest.mark.parametrize(
    ("action", "output", "expected"),
    [
        ("inspect", "matching-rolled-back\n", "matching-rolled-back"),
        ("rollback", "preflight-rolled-back\n", "preflight-rolled-back"),
    ],
)
def test_remote_transport_accepts_recovery_state_outputs(
    tmp_path, action, output, expected
):
    def runner(args, stdin):
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    assert pitr_remote_execution.run_remote_release_action(
        node=PATRONI_NODES[0],
        context=_context(tmp_path),
        action=action,
        txid=TXID,
        release_bundle="{}" if action == "inspect" else None,
        runner=runner,
    ) == expected
