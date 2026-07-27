import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.ha import pitr_communications_cutover as cutover
from scripts.ha.pitr_pinned_ssh import PatroniNode, PinnedSshContext


TXID = "0123456789abcdef0123456789abcdef"


def _remote_namespace(
    tmp_path: Path,
    *,
    gates: tuple[str, str] = ("false", "false"),
    drained: bool = True,
    proof_overrides: list[dict] | None = None,
):
    source = cutover.REMOTE_COMMUNICATIONS_CUTOVER_PREFLIGHT.rsplit(
        "\nif len(sys.argv)", 1
    )[0]
    namespace = {"__name__": "cutover_test"}
    exec(source, namespace)

    project = tmp_path / "project"
    project.mkdir()
    compose = project / "docker-compose.patroni.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    compose.chmod(0o644)
    calls = []
    proof_call_count = 0

    def fake_run_checked(args, **_kwargs):
        nonlocal proof_call_count
        calls.append(tuple(args))
        if args[-3:] == ["config", "--format", "json"]:
            payload = {
                "services": {
                    "communications-worker": {
                        "environment": {
                            "COMMUNICATIONS_WORKER_ENABLED": gates[0],
                            "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE": gates[1],
                        }
                    }
                }
            }
            return subprocess.CompletedProcess(args, 0, json.dumps(payload) + "\n", "")
        if "exec" in args:
            payload = {
                "ok": True,
                "command": "off",
                "drained": drained,
                "runtime_mode": "off",
                "runtime_status": "stopped" if drained else "running",
                "running_delivery_count": 0 if drained else 1,
                "control_revision": 1,
            }
            if proof_overrides is not None:
                if proof_call_count >= len(proof_overrides):
                    raise AssertionError("unexpected extra off/drained proof")
                payload.update(proof_overrides[proof_call_count])
            proof_call_count += 1
            return subprocess.CompletedProcess(args, 0, json.dumps(payload) + "\n", "")
        if "stop" in args or "ps" in args:
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    namespace.update(
        {
            "ROOT_UID": os.geteuid(),
            "ROOT_GID": os.getegid(),
            "GLOBAL_LOCK": str(tmp_path / "global.lock"),
            "MAINTENANCE_MARKER": str(tmp_path / "maintenance"),
            "PROJECT_COMPOSE": {str(project): str(compose)},
            "validate_parent": lambda _path: None,
        }
    )
    namespace["run_checked"] = fake_run_checked
    return namespace, project, calls


def test_remote_preflight_proves_off_drained_and_latches_both_fences(tmp_path):
    namespace, project, calls = _remote_namespace(tmp_path)

    namespace["execute"](TXID, str(project), "docker-compose.patroni.yml")

    receipt = project / ".ha-communications-cutover-preflight"
    release_fence = project / ".ha-communications-worker-release-fenced"
    maintenance = tmp_path / "maintenance"
    assert receipt.read_text(encoding="ascii") == (
        f"communications-off-drained-v1\n{TXID}\n"
    )
    assert release_fence.read_text(encoding="ascii") == "fenced\n"
    assert maintenance.read_text(encoding="ascii") == f"{TXID}\n"
    for path in (receipt, release_fence, maintenance):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert any("exec" in command for command in calls)
    assert any("stop" in command for command in calls)
    assert any("ps" in command for command in calls)
    assert sum("exec" in command for command in calls) == 2
    assert sum("ps" in command for command in calls) == 2


def test_remote_preflight_same_transaction_reproves_and_other_tx_is_fenced(
    tmp_path,
):
    namespace, project, calls = _remote_namespace(tmp_path)
    namespace["execute"](TXID, str(project), "docker-compose.patroni.yml")

    calls.clear()
    namespace["execute"](TXID, str(project), "docker-compose.patroni.yml")
    assert any("exec" in command for command in calls)
    assert (tmp_path / "maintenance").read_text(encoding="ascii") == f"{TXID}\n"

    calls.clear()
    with pytest.raises(
        RuntimeError,
        match="another PITR release owns the maintenance marker",
    ):
        namespace["execute"](
            "1" * 32,
            str(project),
            "docker-compose.patroni.yml",
        )
    assert not calls
    assert (tmp_path / "maintenance").read_text(encoding="ascii") == f"{TXID}\n"


def test_remote_preflight_rejects_concurrent_enable_after_first_proof(tmp_path):
    namespace, project, calls = _remote_namespace(
        tmp_path,
        proof_overrides=[
            {},
            {
                "drained": False,
                "runtime_mode": "all",
                "runtime_status": "running",
                "running_delivery_count": 1,
                "control_revision": 2,
            },
        ],
    )

    with pytest.raises(RuntimeError, match="did not prove off and drained"):
        namespace["execute"](TXID, str(project), "docker-compose.patroni.yml")

    assert sum("exec" in command for command in calls) == 2
    assert sum("ps" in command for command in calls) == 1
    assert (project / ".ha-communications-worker-release-fenced").read_text(
        encoding="ascii"
    ) == "fenced\n"
    assert not (project / ".ha-communications-cutover-preflight").exists()
    assert not (tmp_path / "maintenance").exists()


@pytest.mark.parametrize(
    ("gates", "drained", "message"),
    [
        (("TRUE", "false"), True, "profile is not reviewed"),
        (("false", "FALSE"), True, "profile is not reviewed"),
        (("false", "false"), False, "did not prove off and drained"),
    ],
)
def test_remote_preflight_rejects_uppercase_or_incomplete_drain_without_markers(
    tmp_path, gates, drained, message
):
    namespace, project, _calls = _remote_namespace(
        tmp_path,
        gates=gates,
        drained=drained,
    )

    with pytest.raises(RuntimeError, match=message):
        namespace["execute"](TXID, str(project), "docker-compose.patroni.yml")

    assert not (project / ".ha-communications-cutover-preflight").exists()
    assert not (project / ".ha-communications-worker-release-fenced").exists()
    assert not (tmp_path / "maintenance").exists()


def test_local_wrapper_accepts_only_exact_privacy_safe_receipt(tmp_path):
    node = PatroniNode(
        alias="test",
        physical_host="example.invalid",
        user="root",
        project_dir="/opt/air-api",
        compose_file="docker-compose.patroni.yml",
        compose_source=tmp_path / "compose.yml",
        host_key_source=tmp_path / "host-key.pub",
    )
    context = PinnedSshContext(
        identity_file=tmp_path / "id",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "config",
    )
    calls = []

    def runner(args, stdin):
        calls.append((args, stdin))
        return subprocess.CompletedProcess(
            args,
            0,
            "communications_cutover_preflight=verified\n",
            "",
        )

    cutover.run_remote_communications_cutover_preflight(
        node=node,
        context=context,
        transaction_id=TXID,
        runner=runner,
    )
    assert len(calls) == 1
    assert calls[0][1] is None


def test_local_wrapper_redacts_remote_failure_detail(tmp_path):
    node = PatroniNode(
        alias="test",
        physical_host="example.invalid",
        user="root",
        project_dir="/opt/air-api",
        compose_file="docker-compose.patroni.yml",
        compose_source=tmp_path / "compose.yml",
        host_key_source=tmp_path / "host-key.pub",
    )
    context = PinnedSshContext(
        identity_file=tmp_path / "id",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "config",
    )
    secret = "telegram-token-and-customer-data"

    def runner(args, stdin):
        return subprocess.CompletedProcess(args, 1, "", secret)

    with pytest.raises(RuntimeError) as error:
        cutover.run_remote_communications_cutover_preflight(
            node=node,
            context=context,
            transaction_id=TXID,
            runner=runner,
        )
    assert secret not in str(error.value)
