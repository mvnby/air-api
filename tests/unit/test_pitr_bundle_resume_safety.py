import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import pitr_bundle_transport as bundle
from scripts.ha import pitr_remote_execution
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES
from tests.unit.test_pitr_bundle_transport import (
    TXID,
    _context,
    _payload,
    _remote_namespace,
    _write,
)


def test_existing_transaction_digest_mismatch_preserves_every_generation(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    original, _ = _payload(namespace, project, compose, tool)
    changed, _ = _payload(
        namespace,
        project,
        compose,
        tool,
        tool_content=b"different-release",
    )

    assert namespace["execute"](
        "apply", TXID, str(project), compose.name, original
    ) == "applied"
    txdir = Path(namespace["TRANSACTION_ROOT"]) / TXID
    journal = (txdir / "journal.json").read_bytes()
    marker = Path(namespace["MAINTENANCE_MARKER"]).read_bytes()
    generations = (compose.read_bytes(), tool.read_bytes())

    with pytest.raises(RuntimeError, match="belongs to another release"):
        namespace["execute"](
            "apply", TXID, str(project), compose.name, changed
        )

    assert (txdir / "journal.json").read_bytes() == journal
    assert Path(namespace["MAINTENANCE_MARKER"]).read_bytes() == marker
    assert (compose.read_bytes(), tool.read_bytes()) == generations
    assert not (Path(namespace["ROLLBACK_RECEIPT_ROOT"]) / f"{TXID}.json").exists()


def test_transport_accepts_exact_resumed_result(tmp_path):
    def runner(args, stdin):
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="resumed\n",
            stderr="",
        )

    assert pitr_remote_execution.run_remote_release_action(
        node=PATRONI_NODES[0],
        context=_context(tmp_path),
        action="apply",
        txid=TXID,
        runner=runner,
    ) == "resumed"


def test_inspect_barrier_classifies_without_mutating_release_state(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    changed, _ = _payload(
        namespace,
        project,
        compose,
        tool,
        tool_content=b"different-release",
    )

    assert namespace["execute"](
        "inspect", TXID, str(project), compose.name, payload
    ) == "fresh"
    assert not Path(namespace["STATE_ROOT"]).exists()
    assert not Path(namespace["MAINTENANCE_MARKER"]).exists()

    assert namespace["execute"](
        "apply", TXID, str(project), compose.name, payload
    ) == "applied"
    txdir = Path(namespace["TRANSACTION_ROOT"]) / TXID
    journal = (txdir / "journal.json").read_bytes()
    marker = Path(namespace["MAINTENANCE_MARKER"]).read_bytes()
    assert namespace["execute"](
        "inspect", TXID, str(project), compose.name, payload
    ) == "matching-active"
    with pytest.raises(RuntimeError, match="belongs to another release"):
        namespace["execute"](
            "inspect", TXID, str(project), compose.name, changed
        )
    assert (txdir / "journal.json").read_bytes() == journal
    assert Path(namespace["MAINTENANCE_MARKER"]).read_bytes() == marker

    assert namespace["execute"](
        "finalize", TXID, str(project), compose.name, b""
    ) == "finalized"
    assert namespace["execute"](
        "inspect", TXID, str(project), compose.name, payload
    ) == "matching-finalized"
    assert not Path(namespace["MAINTENANCE_MARKER"]).exists()


def test_inspect_recovers_durable_receipt_when_transaction_directory_remains(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    namespace["execute"]("apply", TXID, str(project), compose.name, payload)
    remove_transaction = namespace["safe_remove_transaction"]
    namespace["safe_remove_transaction"] = lambda _path: (_ for _ in ()).throw(
        RuntimeError("simulated cleanup crash")
    )
    with pytest.raises(RuntimeError, match="simulated cleanup crash"):
        namespace["execute"](
            "rollback", TXID, str(project), compose.name, b""
        )
    namespace["safe_remove_transaction"] = remove_transaction

    txdir = Path(namespace["TRANSACTION_ROOT"]) / TXID
    assert txdir.exists()
    assert (Path(namespace["ROLLBACK_RECEIPT_ROOT"]) / f"{TXID}.json").exists()
    assert namespace["execute"](
        "inspect", TXID, str(project), compose.name, payload
    ) == "matching-rolled-back"
    assert namespace["execute"](
        "rollback", TXID, str(project), compose.name, b""
    ) == "already-rolled-back"
    assert not txdir.exists()


def test_pinned_bundle_bytes_survive_source_changes_between_inspect_and_apply(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir()
    compose = tmp_path / "compose.yml"
    compose.write_bytes(b"old-compose")
    source = tmp_path / "tool"
    source.write_bytes(b"old-tool")
    source.chmod(0o600)
    compose_remote = f"{project}/docker-compose.patroni.yml"
    tool_remote = f"{project}/tool"
    node = SimpleNamespace(
        alias="pinned-node",
        project_dir=str(project),
        compose_file="docker-compose.patroni.yml",
        compose_source=compose,
    )
    asset = SimpleNamespace(source=source, remote_path=tool_remote, mode=0o755)
    monkeypatch.setattr(bundle, "PROJECT_COMPOSE_PATHS", {str(project): compose_remote})
    monkeypatch.setattr(bundle, "BASE_REMOTE_ASSET_MODES", {tool_remote: 0o755})
    pinned = bundle.prepare_release_bundles((node,), (asset,))[str(project)]

    source.write_bytes(b"changed-tool")
    compose.write_bytes(b"changed-compose")
    captured = []

    def runner(args, stdin):
        captured.append(stdin)
        output = "fresh\n" if len(captured) == 1 else "applied\n"
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    for action in ("inspect", "apply"):
        bundle.run_remote_release_action(
            node=node,
            context=_context(tmp_path),
            action=action,
            txid=TXID,
            assets=(asset,),
            release_bundle=pinned,
            runner=runner,
        )

    assert captured == [pinned, pinned]
    files = {item["path"]: item for item in json.loads(pinned)["files"]}
    assert base64.b64decode(files[tool_remote]["content"]) == b"old-tool"
    assert base64.b64decode(files[compose_remote]["content"]) == b"old-compose"


def test_prepare_reads_shared_assets_once_for_every_node(tmp_path, monkeypatch):
    source = tmp_path / "shared-tool"
    source.write_bytes(b"one-shared-generation")
    source.chmod(0o600)
    tool_remote = "/usr/local/sbin/shared-tool"
    nodes = []
    compose_paths = {}
    for alias in ("first", "second"):
        project = tmp_path / alias
        project.mkdir()
        compose = tmp_path / f"{alias}.yml"
        compose.write_text(f"name: {alias}\n", encoding="utf-8")
        compose_remote = f"{project}/docker-compose.patroni.yml"
        compose_paths[str(project)] = compose_remote
        nodes.append(
            SimpleNamespace(
                alias=alias,
                project_dir=str(project),
                compose_file="docker-compose.patroni.yml",
                compose_source=compose,
            )
        )
    asset = SimpleNamespace(source=source, remote_path=tool_remote, mode=0o755)
    monkeypatch.setattr(bundle, "PROJECT_COMPOSE_PATHS", compose_paths)
    monkeypatch.setattr(bundle, "BASE_REMOTE_ASSET_MODES", {tool_remote: 0o755})
    original_read = bundle._read_local_asset
    reads = []

    def counted_read(path):
        reads.append(Path(path))
        return original_read(Path(path))

    monkeypatch.setattr(bundle, "_read_local_asset", counted_read)
    prepared = bundle.prepare_release_bundles(tuple(nodes), (asset,))

    assert reads.count(source) == 1
    shared_digests = {
        next(
            item["sha256"]
            for item in json.loads(payload)["files"]
            if item["path"] == tool_remote
        )
        for payload in prepared.values()
    }
    assert len(shared_digests) == 1
