import ast
import base64
import hashlib
import io
import json
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import pitr_bundle_executor_prelude, pitr_bundle_executor_source
from scripts.ha import pitr_bundle_transport as bundle
from scripts.ha import pitr_remote_execution
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext


TXID = "0123456789abcdef0123456789abcdef"


def _remote_namespace(tmp_path):
    source = bundle.REMOTE_RELEASE_BUNDLE_EXECUTOR.rsplit(
        "\nraise SystemExit(main())", 1
    )[0]
    namespace = {"__name__": "pitr_bundle_executor_test"}
    exec(compile(source, "<pitr-bundle-executor>", "exec"), namespace)
    project = tmp_path / "project"
    project.mkdir(mode=0o700)
    compose = project / "docker-compose.patroni.yml"
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir(mode=0o700)
    tool = tool_dir / "tool"
    state = tmp_path / "state"
    libexec_parent = tmp_path / "libexec"
    namespace.update(
        {
            "ROOT_UID": os.geteuid(),
            "ROOT_GID": os.getegid(),
            "LOCK_PATH": str(tmp_path / "pitr.lock"),
            "STATE_ROOT": str(state),
            "TRANSACTION_ROOT": str(state / "release-transactions"),
            "ROLLBACK_RECEIPT_ROOT": str(state / "rollback-receipts"),
            "RELEASE_MANIFEST": str(state / "release-manifest.json"),
            "MAINTENANCE_MARKER": str(tmp_path / "maintenance"),
            "OPERATION_ROOT": str(tmp_path / "operations"),
            "LIBEXEC_PARENT": str(libexec_parent),
            "LIBEXEC_DIR": str(libexec_parent / "mvn-pitr"),
            "BASE_MODES": {str(tool): 0o755},
            "PROJECT_COMPOSE": {str(project): str(compose)},
            "validate_parent": lambda _path: None,
            "daemon_reload": lambda: None,
        }
    )
    return namespace, project, compose, tool


def _payload(namespace, project, compose, tool, *, tool_content=b"new-tool"):
    contents = {str(compose): b"new-compose", str(tool): tool_content}
    modes = {str(compose): 0o644, str(tool): 0o755}
    files = [
        {
            "content": base64.b64encode(contents[path]).decode("ascii"),
            "mode": modes[path],
            "path": path,
            "sha256": hashlib.sha256(contents[path]).hexdigest(),
        }
        for path in sorted(contents)
    ]
    body = {"files": files, "project_dir": str(project), "version": 1}
    value = {
        **body,
        "release_sha256": hashlib.sha256(namespace["canonical"](body)).hexdigest(),
    }
    return namespace["canonical"](value), value


def _write(path, content, mode):
    path.write_bytes(content)
    path.chmod(mode)


def _context(tmp_path):
    return PinnedSshContext(
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "ssh-config",
    )


def test_embedded_release_executor_is_valid_isolated_python():
    assert (
        bundle.REMOTE_RELEASE_BUNDLE_EXECUTOR
        is pitr_bundle_executor_source.REMOTE_RELEASE_BUNDLE_EXECUTOR
    )
    assert len(Path(bundle.__file__).read_text().splitlines()) < 700
    assert len(Path(pitr_bundle_executor_source.__file__).read_text().splitlines()) < 700
    assert len(Path(pitr_bundle_executor_prelude.__file__).read_text().splitlines()) < 700
    ast.parse(bundle.REMOTE_RELEASE_BUNDLE_EXECUTOR)
    result = subprocess.run(
        [sys.executable, "-I", "-c", bundle.REMOTE_RELEASE_BUNDLE_EXECUTOR],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 64
    assert "invalid invocation" in result.stderr


def test_real_bundle_is_deterministic_complete_and_bounded():
    source = bundle.REMOTE_RELEASE_BUNDLE_EXECUTOR.rsplit(
        "\nraise SystemExit(main())", 1
    )[0]
    remote = {"__name__": "pitr_bundle_policy_test"}
    exec(compile(source, "<pitr-bundle-policy>", "exec"), remote)
    for node in PATRONI_NODES:
        first = pitr_remote_execution.build_host_release_bundle(node)
        second = pitr_remote_execution.build_host_release_bundle(node)
        assert first == second
        assert len(first.encode()) <= bundle.MAX_RELEASE_BUNDLE_BYTES
        value = json.loads(first)
        assert [item["path"] for item in value["files"]] == sorted(
            bundle.expected_remote_asset_modes(node)
        )
        assert set(bundle.expected_remote_asset_modes(node)) == set(
            json.loads(pitr_remote_execution.render_host_asset_manifest(node))
        )
        assert remote["expected_modes"](node.project_dir, node.compose_file) == (
            bundle.expected_remote_asset_modes(node)
        )


def test_local_builder_rejects_missing_extra_mode_and_symlink(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    source = tmp_path / "tool"
    source.write_text("tool\n", encoding="utf-8")
    source.chmod(0o600)
    node = SimpleNamespace(
        project_dir=str(project),
        compose_file="docker-compose.patroni.yml",
        compose_source=compose,
    )
    compose_remote = f"{project}/docker-compose.patroni.yml"
    tool_remote = f"{project}/tool"
    monkeypatch.setattr(bundle, "PROJECT_COMPOSE_PATHS", {str(project): compose_remote})
    monkeypatch.setattr(bundle, "BASE_REMOTE_ASSET_MODES", {tool_remote: 0o755})
    valid = SimpleNamespace(source=source, remote_path=tool_remote, mode=0o755)
    assert json.loads(bundle.build_release_bundle(node, [valid]))["files"]

    with pytest.raises(RuntimeError, match="missing or extra"):
        bundle.build_release_bundle(node, [])
    with pytest.raises(RuntimeError, match="unreviewed"):
        bundle.build_release_bundle(
            node, [SimpleNamespace(source=source, remote_path=tool_remote, mode=0o644)]
        )
    with pytest.raises(RuntimeError, match="unreviewed"):
        bundle.build_release_bundle(
            node,
            [valid, SimpleNamespace(source=source, remote_path="/tmp/extra", mode=0o755)],
        )
    linked = tmp_path / "linked"
    linked.symlink_to(source)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        bundle.build_release_bundle(
            node,
            [SimpleNamespace(source=linked, remote_path=tool_remote, mode=0o755)],
        )


def test_decoder_rejects_traversal_missing_extra_digest_and_mode(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    payload, valid = _payload(namespace, project, compose, tool)
    namespace["decode_bundle"](payload, str(project), compose.name)

    mutations = []
    missing = json.loads(payload)
    missing["files"].pop()
    mutations.append(missing)
    extra = json.loads(payload)
    extra["files"].append(
        {"content": "", "mode": 0o755, "path": str(project / "../escape"), "sha256": hashlib.sha256(b"").hexdigest()}
    )
    mutations.append(extra)
    wrong_mode = json.loads(payload)
    wrong_mode["files"][0]["mode"] = 0o777
    mutations.append(wrong_mode)
    wrong_digest = json.loads(payload)
    wrong_digest["files"][0]["sha256"] = "0" * 64
    mutations.append(wrong_digest)
    for value in mutations:
        with pytest.raises(RuntimeError):
            namespace["decode_bundle"](
                namespace["canonical"](value), str(project), compose.name
            )


def test_payload_reader_rejects_oversize_and_unexpected_input(tmp_path):
    namespace, *_ = _remote_namespace(tmp_path)
    with pytest.raises(RuntimeError, match="size"):
        namespace["read_payload"](
            io.BytesIO(b"x" * (namespace["MAX_BUNDLE"] + 1)), True
        )
    with pytest.raises(RuntimeError, match="size"):
        namespace["read_payload"](io.BytesIO(b"unexpected"), False)


def test_apply_resumes_mixed_old_new_generation_and_finalize(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)

    assert namespace["execute"]("apply", TXID, str(project), compose.name, payload) == "applied"
    _write(tool, b"old-tool", 0o755)
    assert compose.read_bytes() == b"new-compose"
    assert namespace["execute"]("apply", TXID, str(project), compose.name, payload) == "applied"
    assert tool.read_bytes() == b"new-tool"

    assert namespace["execute"]("finalize", TXID, str(project), compose.name, b"") == "finalized"
    assert not Path(namespace["MAINTENANCE_MARKER"]).exists()
    assert not (Path(namespace["TRANSACTION_ROOT"]) / TXID).exists()
    manifest = json.loads(Path(namespace["RELEASE_MANIFEST"]).read_text())
    assert manifest["txid"] == TXID
    assert namespace["execute"]("finalize", TXID, str(project), compose.name, b"") == "already-finalized"
    assert namespace["execute"]("apply", TXID, str(project), compose.name, payload) == "reopened"
    assert not (Path(namespace["TRANSACTION_ROOT"]) / TXID).exists()
    assert Path(namespace["MAINTENANCE_MARKER"]).read_text() == TXID + "\n"
    assert namespace["execute"]("finalize", TXID, str(project), compose.name, b"") == "already-finalized"
    assert not Path(namespace["MAINTENANCE_MARKER"]).exists()


def test_apply_accepts_only_exact_previous_manifest_missing_new_safe_lock_helper(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    old_payload, _ = _payload(namespace, project, compose, tool)
    old_txid = "1" * 32
    assert namespace["execute"](
        "apply", old_txid, str(project), compose.name, old_payload
    ) == "applied"
    assert namespace["execute"](
        "finalize", old_txid, str(project), compose.name, b""
    ) == "finalized"

    helper = tool.parent / "safe_deploy_lock.py"
    helper_content = b"new-helper"
    namespace["BASE_MODES"][str(helper)] = 0o755
    namespace["PREVIOUS_RELEASE_ADDITIONS"] = {str(helper)}
    value = json.loads(old_payload)
    value["files"].append(
        {
            "content": base64.b64encode(helper_content).decode("ascii"),
            "mode": 0o755,
            "path": str(helper),
            "sha256": hashlib.sha256(helper_content).hexdigest(),
        }
    )
    value["files"].sort(key=lambda item: item["path"])
    body = {
        "files": value["files"],
        "project_dir": str(project),
        "version": 1,
    }
    value["release_sha256"] = hashlib.sha256(
        namespace["canonical"](body)
    ).hexdigest()
    new_payload = namespace["canonical"](value)

    assert namespace["execute"](
        "apply", "2" * 32, str(project), compose.name, new_payload
    ) == "applied"
    assert helper.read_bytes() == helper_content

    manifest = json.loads(Path(namespace["RELEASE_MANIFEST"]).read_text())
    manifest["files"].pop()
    Path(namespace["RELEASE_MANIFEST"]).write_bytes(
        namespace["canonical"](manifest) + b"\n"
    )
    with pytest.raises(RuntimeError, match="path set is incomplete"):
        namespace["read_release_manifest"](
            namespace["expected_modes"](str(project), compose.name),
            str(project),
            allow_previous=True,
        )


def test_finalized_transaction_rejects_changed_release_and_manifest_drift(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    namespace["execute"]("apply", TXID, str(project), compose.name, payload)
    namespace["execute"]("finalize", TXID, str(project), compose.name, b"")

    changed, _ = _payload(
        namespace, project, compose, tool, tool_content=b"different-release"
    )
    with pytest.raises(RuntimeError, match="already finalized another release"):
        namespace["execute"]("apply", TXID, str(project), compose.name, changed)

    manifest_path = Path(namespace["RELEASE_MANIFEST"])
    manifest = json.loads(manifest_path.read_text())
    manifest.pop("files")
    manifest_path.write_bytes(namespace["canonical"](manifest) + b"\n")
    manifest_path.chmod(0o600)
    marker = Path(namespace["MAINTENANCE_MARKER"])
    marker.write_text(TXID + "\n")
    marker.chmod(0o600)
    with pytest.raises(RuntimeError, match="manifest contract"):
        namespace["execute"]("finalize", TXID, str(project), compose.name, b"")
    assert marker.read_text() == TXID + "\n"


def test_rollback_restores_exact_snapshot_and_absence(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    payload, _ = _payload(namespace, project, compose, tool)
    assert not tool.exists()

    namespace["execute"]("apply", TXID, str(project), compose.name, payload)
    assert namespace["execute"]("rollback", TXID, str(project), compose.name, b"") == "rolled-back"
    assert compose.read_bytes() == b"old-compose"
    assert stat.S_IMODE(compose.stat().st_mode) == 0o644
    assert not tool.exists()
    assert not Path(namespace["MAINTENANCE_MARKER"]).exists()
    receipt = json.loads(
        (Path(namespace["ROLLBACK_RECEIPT_ROOT"]) / f"{TXID}.json").read_text()
    )
    generations = {item["path"]: item for item in receipt["old_generations"]}
    assert generations[str(compose)]["sha256"] == hashlib.sha256(
        b"old-compose"
    ).hexdigest()
    assert generations[str(tool)]["present"] is False
    assert namespace["execute"]("rollback", TXID, str(project), compose.name, b"") == "already-rolled-back"
    with pytest.raises(RuntimeError, match="already has a rollback receipt"):
        namespace["execute"]("apply", TXID, str(project), compose.name, payload)


def test_rollback_without_transaction_or_receipt_keeps_marker_fenced(tmp_path):
    namespace, project, compose, _tool = _remote_namespace(tmp_path)
    marker = Path(namespace["MAINTENANCE_MARKER"])
    marker.write_text(TXID + "\n")
    marker.chmod(0o600)
    with pytest.raises(FileNotFoundError):
        namespace["execute"]("rollback", TXID, str(project), compose.name, b"")
    assert marker.read_text() == TXID + "\n"


def test_rollback_receipt_closes_both_cleanup_crash_windows(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    namespace["execute"]("apply", TXID, str(project), compose.name, payload)

    remove_transaction = namespace["safe_remove_transaction"]
    namespace["safe_remove_transaction"] = lambda _path: (_ for _ in ()).throw(
        RuntimeError("crash before transaction cleanup")
    )
    with pytest.raises(RuntimeError, match="crash before"):
        namespace["execute"]("rollback", TXID, str(project), compose.name, b"")
    receipt_path = Path(namespace["ROLLBACK_RECEIPT_ROOT"]) / f"{TXID}.json"
    assert receipt_path.exists()
    assert (Path(namespace["TRANSACTION_ROOT"]) / TXID).exists()
    assert Path(namespace["MAINTENANCE_MARKER"]).exists()
    (Path(namespace["TRANSACTION_ROOT"]) / TXID / "journal.json").unlink()
    namespace["safe_remove_transaction"] = remove_transaction
    assert namespace["execute"]("rollback", TXID, str(project), compose.name, b"") == "already-rolled-back"

    second_txid = "1" * 32
    namespace["execute"]("apply", second_txid, str(project), compose.name, payload)
    remove_marker = namespace["remove_marker"]
    namespace["remove_marker"] = lambda _txid: (_ for _ in ()).throw(
        RuntimeError("crash before marker cleanup")
    )
    with pytest.raises(RuntimeError, match="crash before marker"):
        namespace["execute"]("rollback", second_txid, str(project), compose.name, b"")
    assert not (Path(namespace["TRANSACTION_ROOT"]) / second_txid).exists()
    assert Path(namespace["MAINTENANCE_MARKER"]).read_text() == second_txid + "\n"
    namespace["remove_marker"] = remove_marker
    assert namespace["execute"]("rollback", second_txid, str(project), compose.name, b"") == "already-rolled-back"


def test_receipt_only_rollback_fences_tamper_and_noncanonical_receipt(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    payload, _ = _payload(namespace, project, compose, tool)
    namespace["execute"]("apply", TXID, str(project), compose.name, payload)
    namespace["execute"]("rollback", TXID, str(project), compose.name, b"")

    _write(compose, b"tampered", 0o644)
    with pytest.raises(RuntimeError, match="does not match"):
        namespace["execute"]("rollback", TXID, str(project), compose.name, b"")
    _write(compose, b"old-compose", 0o644)
    receipt_path = Path(namespace["ROLLBACK_RECEIPT_ROOT"]) / f"{TXID}.json"
    parsed = json.loads(receipt_path.read_text())
    receipt_path.write_text(json.dumps(parsed, indent=2) + "\n")
    receipt_path.chmod(0o600)
    with pytest.raises(RuntimeError, match="not canonical"):
        namespace["execute"]("rollback", TXID, str(project), compose.name, b"")
    parsed["project_dir"] = "/opt/not-this-project"
    receipt_path.write_bytes(namespace["canonical"](parsed) + b"\n")
    receipt_path.chmod(0o600)
    with pytest.raises(RuntimeError, match="contract is invalid"):
        namespace["execute"]("rollback", TXID, str(project), compose.name, b"")


def test_symlink_unknown_generation_and_marker_conflict_fence(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    target = tmp_path / "target"
    target.write_bytes(b"target")
    tool.symlink_to(target)
    payload, _ = _payload(namespace, project, compose, tool)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        namespace["execute"]("apply", TXID, str(project), compose.name, payload)

    tool.unlink()
    namespace["execute"]("apply", TXID, str(project), compose.name, payload)
    _write(tool, b"unknown", 0o755)
    with pytest.raises(RuntimeError, match="unknown generation"):
        namespace["execute"]("apply", TXID, str(project), compose.name, payload)
    assert Path(namespace["MAINTENANCE_MARKER"]).read_text() == TXID + "\n"

    other = "f" * 32
    Path(namespace["MAINTENANCE_MARKER"]).write_text(other + "\n")
    Path(namespace["MAINTENANCE_MARKER"]).chmod(0o600)
    with pytest.raises(RuntimeError, match="owns the maintenance marker"):
        namespace["execute"]("apply", TXID, str(project), compose.name, payload)


def test_hardlink_and_operation_record_block_release(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    hardlink = tmp_path / "tool-hardlink"
    os.link(tool, hardlink)
    payload, _ = _payload(namespace, project, compose, tool)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        namespace["execute"]("apply", TXID, str(project), compose.name, payload)

    hardlink.unlink()
    operation_root = Path(namespace["OPERATION_ROOT"])
    operation_root.mkdir(mode=0o700)
    (operation_root / "active.json").write_text("{}\n")
    with pytest.raises(RuntimeError, match="recorded PITR operation"):
        namespace["execute"]("apply", TXID, str(project), compose.name, payload)


def test_remote_action_uses_pinned_ssh_and_stdin_only_for_apply(tmp_path):
    captured = []

    def runner(args, stdin):
        captured.append((list(args), stdin))
        action = shlex.split(args[-1])[4]
        output = {"apply": "applied\n", "finalize": "finalized\n"}[action]
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    node = PATRONI_NODES[0]
    result = pitr_remote_execution.run_remote_release_action(
        node=node,
        context=_context(tmp_path),
        action="apply",
        txid=TXID,
        runner=runner,
    )
    assert result == "applied"
    args, stdin = captured[-1]
    command = shlex.split(args[-1])
    assert command[:4] == [
        "/usr/bin/python3",
        "-I",
        "-c",
        bundle.REMOTE_RELEASE_BUNDLE_EXECUTOR,
    ]
    assert command[4:] == ["apply", TXID, node.project_dir, node.compose_file]
    assert json.loads(stdin)["project_dir"] == node.project_dir
    assert json.loads(stdin)["release_sha256"] not in args[-1]

    pitr_remote_execution.run_remote_release_action(
        node=node,
        context=_context(tmp_path),
        action="finalize",
        txid=TXID,
        runner=runner,
    )
    assert captured[-1][1] is None


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        ("finalized", ""),
        ("finalized\nextra\n", ""),
        ("applied\n", ""),
        ("finalized\n", "warning\n"),
    ],
)
def test_remote_action_rejects_nonexact_success_output(tmp_path, stdout, stderr):
    def runner(args, stdin):
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr=stderr)

    with pytest.raises(RuntimeError, match="unexpected output"):
        pitr_remote_execution.run_remote_release_action(
            node=PATRONI_NODES[0],
            context=_context(tmp_path),
            action="finalize",
            txid=TXID,
            runner=runner,
        )


def test_remote_action_accepts_exact_idempotent_rollback_output(tmp_path):
    def runner(args, stdin):
        return subprocess.CompletedProcess(
            args, 0, stdout="already-rolled-back\n", stderr=""
        )

    assert pitr_remote_execution.run_remote_release_action(
        node=PATRONI_NODES[0],
        context=_context(tmp_path),
        action="rollback",
        txid=TXID,
        runner=runner,
    ) == "already-rolled-back"


def test_parent_and_lock_write_policy_is_fail_closed(tmp_path):
    namespace, project, _compose, _tool = _remote_namespace(tmp_path)

    def metadata(mode, *, uid=None, gid=None):
        return SimpleNamespace(
            st_mode=stat.S_IFDIR | mode,
            st_uid=os.geteuid() if uid is None else uid,
            st_gid=os.getegid() if gid is None else gid,
        )

    policy = namespace["unsafe_parent_metadata"]
    assert policy("/opt/air-api", metadata(0o755)) is False
    assert policy("/opt/air-api", metadata(0o775)) is True
    assert policy("/opt/air-api", metadata(0o1777)) is True
    assert policy("/run/lock", metadata(0o775)) is False
    assert policy("/run/lock", metadata(0o1777)) is False
    assert policy("/run/lock", metadata(0o777)) is True
    assert policy("/run/lock", metadata(0o755, gid=os.getegid() + 1)) is True

    bad_lock = Path(namespace["LOCK_PATH"])
    bad_lock.write_text("")
    bad_lock.chmod(0o660)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        namespace["open_lock"](str(bad_lock))
    bad_lock.unlink()

    deploy_lock = project / ".deploy.lock"
    deploy_lock.write_text("")
    deploy_lock.chmod(0o644)
    descriptor = namespace["open_lock"](str(deploy_lock))
    try:
        assert stat.S_IMODE(deploy_lock.stat().st_mode) == 0o600
    finally:
        os.close(descriptor)
    with pytest.raises(RuntimeError, match="unreviewed release lock"):
        namespace["open_lock"](str(tmp_path / "other.lock"))


def test_installer_and_blue_green_siblings_are_attested():
    manifest = json.loads(
        pitr_remote_execution.render_host_asset_manifest(PATRONI_NODES[0])
    )
    expected = {
        "/usr/local/libexec/mvn-pitr/install_postgres_pitr_units.sh",
        "/usr/local/libexec/mvn-pitr/run_postgres_pitr_install_locked.py",
        "/usr/local/libexec/mvn-pitr/deploy_backend_blue_green.sh",
        "/usr/local/libexec/mvn-pitr/deploy_backend_blue_green_safety.sh",
        "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py",
        "/usr/local/libexec/mvn-pitr/prepare_google_oauth_token_dir.sh",
    }
    assert expected <= set(manifest)
    helper_path = "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py"
    helper_source = Path(pitr_remote_execution.REPO_ROOT) / "scripts/ha/safe_deploy_lock.py"
    assert manifest[helper_path] == hashlib.sha256(helper_source.read_bytes()).hexdigest()
    release = json.loads(
        pitr_remote_execution.build_host_release_bundle(PATRONI_NODES[0])
    )
    helper_entry = next(item for item in release["files"] if item["path"] == helper_path)
    assert helper_entry["mode"] == 0o755
    assert helper_entry["sha256"] == manifest[helper_path]
    for path in expected:
        assert f'"{path}": 0o755' in pitr_remote_execution.REMOTE_ASSET_ATTESTATION
    wrapper = pitr_remote_execution.LOCKED_MAINTENANCE_WRAPPER
    assert '"API_DEPLOY_LOCK_FD": "9"' in wrapper
    assert '"API_DEPLOY_LOCK_FILE": os.path.join(project_dir, ".deploy.lock")' in wrapper
    assert '"API_DEPLOY_LOCK_HELPER": "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py"' in wrapper
    assert "os.dup2(deploy_fd, 9, inheritable=True)" in wrapper
    assert "pass_fds = (deploy_fd, secret_fd)" in wrapper
    execute_source = bundle.REMOTE_RELEASE_BUNDLE_EXECUTOR.split("def execute(", 1)[1]
    assert execute_source.index("global_fd = open_lock") < execute_source.index(
        "deploy_fd = open_lock"
    ) < execute_source.index("ensure_roots()")
    assert "stop mvn-patroni-role-agent" not in bundle.REMOTE_RELEASE_BUNDLE_EXECUTOR
