import copy
import json
import os
import stat
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts.ha.patroni_rollout_remote import build_payload, run_remote_action
from scripts.ha.patroni_rollout_remote_executor import REMOTE_EXECUTOR
from scripts.ha.patroni_rollout_local import REVIEWED_ASSETS
from scripts.ha.patroni_rollout_schema import RolloutInputs
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext


CURRENT = "ghcr.io/mvnby/air-api/patroni@sha256:" + "2" * 64
TARGET = "ghcr.io/mvnby/air-api/patroni@sha256:" + "3" * 64


def _inputs():
    return RolloutInputs.validated(
        deploy_sha="1" * 40,
        publish_run_id="123456",
        publish_run_attempt=1,
        transaction_id="0" * 32,
        maintenance_transaction_id="f" * 32,
        current_image=CURRENT,
        target_image=TARGET,
        apply=True,
    )


def test_remote_executor_compiles_and_contains_required_fail_closed_contracts():
    compile(REMOTE_EXECUTOR, "<remote>", "exec")
    assert ".patroni-cutover-in-progress" in REMOTE_EXECUTOR
    assert "/run/mvn-postgres-pitr-maintenance" in REMOTE_EXECUTOR
    assert "--no-env-resolution" in REMOTE_EXECUTOR
    assert "--no-interpolate" in REMOTE_EXECUTOR
    assert '["up", "-d", "--no-deps", "--force-recreate"' in REMOTE_EXECUTOR
    assert '"--pull", "never"' in REMOTE_EXECUTOR
    assert ".mvn-pitr-archive.lock" in REMOTE_EXECUTOR
    assert "[.]partial" in REMOTE_EXECUTOR
    assert "revert_archive_command" in REMOTE_EXECUTOR
    assert "pg_is_in_recovery" in REMOTE_EXECUTOR
    assert "dcs_baseline_sha256" in REMOTE_EXECUTOR
    assert "role_unit_sha256" in REMOTE_EXECUTOR
    assert "exact_role_env" in REMOTE_EXECUTOR
    assert "attest_container_role_environment" in REMOTE_EXECUTOR
    assert '"CLOUDFLARE_PURGE_DRY_RUN": "true"' in REMOTE_EXECUTOR


def _remote_namespace():
    definitions = REMOTE_EXECUTOR.rsplit("\ntry:\n    main()", 1)[0]
    namespace = {"__name__": "patroni_rollout_remote_test"}
    exec(compile(definitions, "<remote-definitions>", "exec"), namespace)
    namespace["ROOT"] = os.geteuid()
    return namespace


def test_rollout_modules_stay_small_and_all_composed_sources_are_reviewed():
    rollout_modules = sorted(
        (Path(__file__).resolve().parents[2] / "scripts/ha").glob("patroni_rollout_*.py")
    ) + [Path(__file__).resolve().parents[2] / "scripts/ha/rollout_patroni_image.py"]
    assert all(len(path.read_text(encoding="utf-8").splitlines()) < 700 for path in rollout_modules)
    for required in (
        "scripts/ha/patroni_rollout_cli.py",
        "scripts/ha/patroni_rollout_remote_contract.py",
        "scripts/ha/patroni_rollout_remote_executor.py",
        "scripts/ha/patroni_rollout_remote_prelude.py",
        "scripts/ha/patroni_rollout_remote_runtime.py",
        "deploy/ha/patroni/mvn-patroni-role-agent.service",
    ):
        assert required in REVIEWED_ASSETS


def test_role_agent_live_generation_rejects_old_process_and_stale_environment(monkeypatch):
    namespace = _remote_namespace()
    expected = {"HA_PROJECT_DIR": "/opt/air-api", "HA_PATRONI_NAME": "mvn-api"}
    monkeypatch.setattr(
        namespace["os"], "lstat",
        lambda _path: SimpleNamespace(st_ctime_ns=2_000_000_000),
    )
    namespace["process_start_ns"] = lambda _pid: 1_999_999_999
    namespace["read_proc_file"] = lambda _path, _maximum=131072: (
        b"HA_PROJECT_DIR=/opt/air-api\0HA_PATRONI_NAME=mvn-api\0"
    )
    with pytest.raises(RuntimeError, match="predates"):
        namespace["validate_role_process_generation"]("123", expected)

    namespace["process_start_ns"] = lambda _pid: 2_000_000_000
    namespace["read_proc_file"] = lambda _path, _maximum=131072: (
        b"HA_PROJECT_DIR=/opt/air-api\0HA_PATRONI_NAME=zakup\0"
    )
    with pytest.raises(RuntimeError, match="live role-agent environment differs"):
        namespace["validate_role_process_generation"]("123", expected)


def test_role_env_rejects_compose_colon_syntax_and_unknown_keys():
    namespace = _remote_namespace()
    canonical, expected = namespace["canonical_role_env"]("standby", False)
    namespace["read_root_file"] = lambda _path: canonical.encode("ascii")
    assert namespace["exact_role_env"]("/role.env", "standby", False) == expected

    hidden_extra = canonical + "COMMUNICATIONS_WORKER_ENABLED: true\n"
    namespace["read_root_file"] = lambda _path: hidden_extra.encode("ascii")
    with pytest.raises(RuntimeError, match="exact canonical generation"):
        namespace["exact_role_env"]("/role.env", "standby", False)


def test_live_container_role_env_rejects_duplicate_or_overridden_values():
    namespace = _remote_namespace()
    expected = {"APP_ROLE": "standby", "SCHEDULER_ENABLED": "false"}
    namespace["compose_args"] = lambda *_args: ["docker", "compose"]
    inspected = [{"State": {"Running": True}, "Config": {"Env": [
        "APP_ROLE=standby", "SCHEDULER_ENABLED=false", "SCHEDULER_ENABLED=true"
    ]}}]
    namespace["run"] = lambda args, **_kwargs: (
        "a" * 12 if args[:3] == ["docker", "compose", "ps"] else json.dumps(inspected)
    )

    with pytest.raises(RuntimeError, match="live container role environment differs"):
        namespace["attest_container_role_environment"](
            "/opt/air-api", "compose.yml", "app", expected
        )


def test_remote_shared_lock_normalizes_only_safe_legacy_inode(monkeypatch):
    namespace = _remote_namespace()
    state = {"mode": 0o644, "nlink": 1, "chmod": []}

    def metadata(mode=None, nlink=None):
        return SimpleNamespace(
            st_mode=stat.S_IFREG | (state["mode"] if mode is None else mode),
            st_uid=namespace["ROOT"], st_gid=namespace["ROOT"],
            st_nlink=state["nlink"] if nlink is None else nlink,
            st_dev=1, st_ino=2,
        )

    def fake_open(_path, flags, *_args):
        if flags & os.O_EXCL:
            raise FileExistsError
        return 17

    monkeypatch.setattr(namespace["os"], "open", fake_open)
    monkeypatch.setattr(namespace["os"], "lstat", lambda _path: metadata())
    monkeypatch.setattr(namespace["os"], "fstat", lambda _fd: metadata())
    monkeypatch.setattr(namespace["os"], "close", lambda _fd: None)

    def fake_chmod(_fd, mode):
        state["chmod"].append(mode)
        state["mode"] = mode

    monkeypatch.setattr(namespace["os"], "fchmod", fake_chmod)
    descriptor = namespace["open_project_lock"]("/opt/air-api")
    assert state["chmod"] == []
    namespace["normalize_locked_project_lock"](descriptor)
    assert state["chmod"] == [0o600]

    for unsafe_mode, unsafe_links in ((0o644, 2), (stat.S_IFLNK, 1)):
        state.update(mode=unsafe_mode, nlink=unsafe_links, chmod=[])
        with pytest.raises(RuntimeError, match="metadata is unsafe"):
            namespace["open_project_lock"]("/opt/air-api")
        assert state["chmod"] == []


def test_pitr_fence_is_bound_to_exact_maintenance_transaction(tmp_path):
    namespace = _remote_namespace()
    marker = tmp_path / "maintenance"
    marker.write_text("a" * 32 + "\n", encoding="ascii")
    marker.chmod(0o600)
    namespace["PITR_MARKER"] = str(marker)
    namespace["read_root_file"] = lambda path, **_kwargs: Path(path).read_bytes()

    namespace["pitr_fence"]("a" * 32)
    with pytest.raises(RuntimeError, match="does not match"):
        namespace["pitr_fence"]("b" * 32)


def test_completed_marker_cleanup_accepts_missing_but_rejects_wrong_owner(tmp_path):
    namespace = _remote_namespace()
    namespace["read_root_file"] = lambda path, **_kwargs: Path(path).read_bytes()
    marker = tmp_path / "cutover"
    namespace["remove_marker_if_owned"](str(marker), "a" * 32)
    marker.write_text("b" * 32 + "\n", encoding="ascii")
    marker.chmod(0o600)
    with pytest.raises(RuntimeError, match="another transaction"):
        namespace["remove_marker_if_owned"](str(marker), "a" * 32)
    marker.write_text("a" * 32 + "\n", encoding="ascii")
    namespace["remove_marker_if_owned"](str(marker), "a" * 32)
    assert not marker.exists()


def test_rollback_rejects_unavailable_patroni_without_positive_sql_standby_proof():
    namespace = _remote_namespace()
    namespace["local_patroni_role"] = lambda: (_ for _ in ()).throw(RuntimeError("down"))
    namespace["run"] = lambda *_args, **_kwargs: "leader"
    namespace["sql"] = lambda *_args: "f"
    with pytest.raises(RuntimeError, match="without exact PostgreSQL standby proof"):
        namespace["require_standby"]("/opt/air-api", "compose.yml", "mvn-api", True)


def test_target_dcs_rejects_any_extra_drift_from_journaled_baseline():
    namespace = _remote_namespace()
    baseline = {
        "loop_wait": 10,
        "postgresql": {"parameters": {
            "archive_mode": "on", "archive_timeout": "300",
            "archive_command": namespace["LEGACY_COMMAND"],
        }},
    }
    target = copy.deepcopy(baseline)
    target["postgresql"]["parameters"]["archive_command"] = namespace["EXPECTED_COMMAND"]
    target["loop_wait"] = 11
    journal = {
        "dcs_baseline": baseline,
        "dcs_baseline_sha256": namespace["sha"](namespace["canonical"](baseline)),
    }
    namespace["yaml_config"] = lambda *_args: target
    with pytest.raises(RuntimeError, match="drifted from the journaled baseline"):
        namespace["check_target_dcs"]("/opt/air-api", "compose.yml", journal)


@pytest.mark.parametrize("operation", ["apply", "revert"])
def test_dcs_retry_rejects_extra_drift_after_a_committed_edit(operation):
    namespace = _remote_namespace()
    baseline = {"loop_wait": 10, "postgresql": {"parameters": {
        "archive_mode": "on", "archive_timeout": "300",
        "archive_command": namespace["LEGACY_COMMAND"],
    }}}
    live = copy.deepcopy(baseline)
    live["postgresql"]["parameters"]["archive_command"] = namespace["EXPECTED_COMMAND"]
    live["loop_wait"] = 11
    journal = {
        "legacy_archive_command": namespace["LEGACY_COMMAND"],
        "dcs_baseline": baseline,
        "dcs_baseline_sha256": namespace["sha"](namespace["canonical"](baseline)),
    }
    namespace["container_id"] = lambda *_args: "db"
    namespace["yaml_config"] = lambda *_args: live
    namespace["run"] = lambda *_args, **_kwargs: pytest.fail("edit-config must not run")
    with pytest.raises(RuntimeError, match="drifted|unreviewed"):
        if operation == "apply":
            namespace["apply_archive_command"](
                "/opt/air-api", "compose.yml", namespace["LEGACY_COMMAND_SHA256"],
                "/journal", journal,
            )
        else:
            namespace["revert_archive_command"](
                "/opt/air-api", "compose.yml", namespace["LEGACY_COMMAND_SHA256"], journal
            )


def test_compensation_rechecks_primary_and_quorum_before_dcs_edit():
    branch = REMOTE_EXECUTOR.split('elif action == "revert-archive-command":', 1)[1].split(
        'elif action == "switchover":', 1
    )[0]
    assert branch.index('local_patroni_role() != "primary"') < branch.index("prove_etcd(payload)")
    assert branch.index("prove_etcd(payload)") < branch.index("revert_archive_command(")


def test_archive_proof_accepts_safe_expected_file_after_archiver_overshoot(monkeypatch):
    namespace = _remote_namespace()
    expected = "000000010000000000000002"
    calls = {"stats": 0}

    def sql(_project, _compose, statement):
        if "pg_switch_wal" in statement:
            return expected
        calls["stats"] += 1
        return ("000000010000000000000001|0" if calls["stats"] == 1
                else "000000010000000000000003|0")

    namespace["sql"] = sql
    monkeypatch.setattr(namespace["os"].path, "exists", lambda _path: True)
    monkeypatch.setattr(namespace["os"], "lstat", lambda _path: SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600, st_uid=70, st_gid=70,
        st_size=16 * 1024 * 1024,
    ))
    assert namespace["prove_archive"]("/opt/air-api", "compose.yml") == expected


def test_payload_extras_cannot_override_immutable_transaction_fields():
    with pytest.raises(RuntimeError, match="unreviewed payload fields"):
        build_payload(
            inputs=_inputs(),
            action="stage",
            compose_contract_sha256="4" * 64,
            helper_sha256="5" * 64,
            extra={"target_image": CURRENT},
        )


def test_publish_run_and_attempt_are_bound_to_every_remote_payload():
    payload = json.loads(
        build_payload(
            inputs=_inputs(),
            action="preflight",
            compose_contract_sha256="4" * 64,
            helper_sha256="5" * 64,
        )
    )

    assert payload["publish_run_id"] == "123456"
    assert payload["publish_run_attempt"] == 1
    assert '"publish_run_id": payload["publish_run_id"]' in REMOTE_EXECUTOR
    assert '"publish_run_attempt": payload["publish_run_attempt"]' in REMOTE_EXECUTOR
    assert '"role_unit_sha256": payload["role_unit_sha256"]' in REMOTE_EXECUTOR


def test_transport_uses_pinned_ssh_and_keeps_credentials_out_of_argv(tmp_path: Path):
    context = PinnedSshContext(
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "config",
    )
    captured = {}

    def runner(args, stdin):
        captured["args"] = list(args)
        captured["stdin"] = stdin
        return subprocess.CompletedProcess(args, 0, "stage=passed\n", "")

    output = run_remote_action(
        action="stage",
        node=PATRONI_NODES[0],
        context=context,
        inputs=_inputs(),
        compose_contract_sha256="4" * 64,
        helper_sha256="5" * 64,
        extra={"ghcr_username": "robot", "ghcr_token": "secret-token"},
        runner=runner,
    )

    assert output == "stage=passed"
    assert captured["args"][:3] == ["ssh", "-F", str(context.config_file)]
    assert all("secret-token" not in argument for argument in captured["args"])
    assert "secret-token" in captured["stdin"]
