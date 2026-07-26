import base64
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ha/run_patroni_node_remote.sh"
TRANSACTION_RUNNER = REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh"
API_HOST_KEY = REPO_ROOT / "deploy/ha/security/mvn-api-ssh-host-key.pub"
RESERVE_HOST_KEY = REPO_ROOT / "deploy/ha/security/zakup-ssh-host-key.pub"
EXPECTED_HOST_KEY_FINGERPRINTS = {
    API_HOST_KEY: "SHA256:sSKU5/aHiQp5pr8ntRWcEXPb4m+Z2rIJRGQP7ojZC0Q",
    RESERVE_HOST_KEY: "SHA256:HoSkXhYVeDMbdQtwvMVstWLAeeBp+NJQPhvCcMri+GQ",
}
FAKE_SSH_KEYGEN = """#!/usr/bin/env python3
import base64
import pathlib
import sys


def read_ssh_string(blob, offset):
    if offset + 4 > len(blob):
        raise ValueError("missing SSH string length")
    size = int.from_bytes(blob[offset : offset + 4], "big")
    start = offset + 4
    end = start + size
    if end > len(blob):
        raise ValueError("truncated SSH string")
    return blob[start:end], end


try:
    if len(sys.argv) != 5 or sys.argv[1] != "-lf" or sys.argv[3:] != ["-E", "sha256"]:
        raise ValueError("unexpected ssh-keygen invocation")
    fields = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").split()
    if len(fields) != 2 or fields[0] != "ssh-ed25519":
        raise ValueError("unexpected public key format")
    blob = base64.b64decode(fields[1], validate=True)
    key_type, offset = read_ssh_string(blob, 0)
    key, offset = read_ssh_string(blob, offset)
    if key_type != b"ssh-ed25519" or len(key) != 32 or offset != len(blob):
        raise ValueError("invalid Ed25519 SSH wire blob")
except (OSError, ValueError):
    raise SystemExit(1)

print("256 SHA256:test no-comment (ED25519)")
"""


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _workflow_job_block(workflow: str, job_name: str) -> str:
    lines = workflow.splitlines()
    marker = f"  {job_name}:"
    start = lines.index(marker)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break
    return "\n".join(lines[start:end])


def _ed25519_sha256_fingerprint(path: Path) -> str:
    fields = path.read_text(encoding="utf-8").split()
    assert len(fields) == 2
    assert fields[0] == "ssh-ed25519"
    blob = base64.b64decode(fields[1], validate=True)

    def read_ssh_string(offset: int) -> tuple[bytes, int]:
        assert offset + 4 <= len(blob)
        size = int.from_bytes(blob[offset : offset + 4], "big")
        start = offset + 4
        end = start + size
        assert end <= len(blob)
        return blob[start:end], end

    key_type, offset = read_ssh_string(0)
    key, offset = read_ssh_string(offset)
    assert key_type == b"ssh-ed25519"
    assert len(key) == 32
    assert offset == len(blob)
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii")
    return f"SHA256:{digest.rstrip('=')}"


def _run_probe(
    tmp_path: Path,
    role: str,
    *,
    host_key_source: Path = API_HOST_KEY,
    node_host: str = "example.invalid",
    node_user: str = "deploy",
    maintenance_marker: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    _executable(fake_bin / "ssh-keygen", FAKE_SSH_KEYGEN)
    _executable(
        fake_bin / "ssh",
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" > \"${SSH_ARGS_LOG:?}\"\n"
        "known_hosts=''\n"
        "identity_file=''\n"
        "take_identity=false\n"
        "for arg in \"$@\"; do\n"
        "  if [[ \"${take_identity}\" == true ]]; then\n"
        "    identity_file=\"${arg}\"\n"
        "    take_identity=false\n"
        "    continue\n"
        "  fi\n"
        "  case \"${arg}\" in\n"
        "    -i) take_identity=true ;;\n"
        "    UserKnownHostsFile=*) known_hosts=\"${arg#*=}\" ;;\n"
        "  esac\n"
        "done\n"
        "test -n \"${known_hosts}\" -a -n \"${identity_file}\"\n"
        "python3 -c 'import os,pathlib,sys; pathlib.Path(sys.argv[3]).write_text("
        "f\"{os.stat(sys.argv[1]).st_mode & 0o777:o} "
        "{os.stat(sys.argv[2]).st_mode & 0o777:o}\")' "
        "\"${identity_file}\" \"${known_hosts}\" \"${SSH_FILE_MODES_CAPTURE:?}\"\n"
        "cp \"${known_hosts}\" \"${SSH_KNOWN_HOSTS_CAPTURE:?}\"\n"
        "remote_command=\"${!#}\"\n"
        "bash -c \"${remote_command}\"\n",
    )
    _executable(
        fake_bin / "curl",
        f"#!/usr/bin/env bash\nprintf '{{\"state\":\"running\",\"role\":\"{role}\"}}\\n'\n",
    )
    return subprocess.run(
        ["bash", str(SCRIPT), "probe"],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "API_NODE_HOST": node_host,
            "API_NODE_USER": node_user,
            "API_NODE_SSH_HOST_KEY_SOURCE": str(host_key_source),
            "SSH_PRIVATE_KEY": "test-private-key",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_RUN_ID": "test-run",
            "GITHUB_JOB": "probe",
            "SSH_ARGS_LOG": str(tmp_path / "ssh-args.log"),
            "SSH_FILE_MODES_CAPTURE": str(tmp_path / "ssh-file-modes.capture"),
            "SSH_KNOWN_HOSTS_CAPTURE": str(tmp_path / "known-hosts.capture"),
            "API_PITR_MAINTENANCE_MARKER": str(
                maintenance_marker or tmp_path / "absent-maintenance-marker"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_remote_orchestrator_has_strict_operations_and_never_manages_database():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "probe|migrate|deploy" in text
    assert text.index("umask 077") < text.index(
        "printf '%s\\n' \"${SSH_PRIVATE_KEY}\" > \"${KEY_PATH}\""
    )
    assert "required_commands=(ssh ssh-keygen)" in text
    assert 'required_commands+=(scp)' in text
    assert "StrictHostKeyChecking=yes" in text
    assert "-F /dev/null" in text
    assert "IdentitiesOnly=yes" in text
    assert "GlobalKnownHostsFile=/dev/null" in text
    assert "UserKnownHostsFile=" in text
    assert "HostKeyAlgorithms=ssh-ed25519" in text
    assert "UpdateHostKeys=no" in text
    assert "ssh-keyscan" not in text
    assert "docker-compose.patroni.yml" in text
    assert "run_patroni_migrations.sh" in text
    assert "deploy_patroni_api_node.sh" in text
    assert "scripts/ha/require_deploy_capacity.sh" in text
    assert "deploy_backend_blue_green.sh" in text
    assert "deploy_backend_blue_green_safety.sh" in text
    assert "prepare_google_oauth_token_dir.sh" in text
    assert 'candidate_id="$(printf' in text
    assert 'REMOTE_COMPOSE_FILE="docker-compose.patroni.candidate.${candidate_id}.yml"' in text
    assert 'PATRONI_CANDIDATE_COMPOSE_SOURCE=$(quote' in text
    assert '"${REMOTE}:${PROJECT_DIR}/${REMOTE_COMPOSE_FILE}"' not in text
    assert "run_patroni_candidate_transaction.sh" in text
    assert "scripts/ha/patroni_compose_db_contract.py" in text
    assert "PATRONI_DB_CONTRACT_HELPER=" in text
    assert "PATRONI_PROXY_CONFIG_SOURCE=" in text
    assert "PATRONI_PROXY_UPSTREAM_SOURCE=" in text
    assert "API_DEPLOY_CAPACITY_HELPER=" in text
    assert "API_DEPLOY_CAPACITY_PROFILE=" in text
    assert 'DEPLOY_CAPACITY_PROFILE=reserve' in text
    assert "mktemp -d /tmp/mvn-patroni-release.XXXXXXXX" in text
    assert "verify_patroni_remote_bundle.py" in text
    assert "BUNDLE_MANIFEST_B64" in text
    assert "python3 -I -c" in text
    assert "${REMOTE}:/tmp/" not in text
    assert "bash /tmp/run_patroni_candidate_transaction.sh" not in text
    assert "patroni-compose-db-contract-${GITHUB_RUN_ID" not in text
    assert "compose_candidate_transaction.sh" in text
    assert "reconcile_backend_compose_runtime.sh" in text
    assert (
        "API_BLUE_GREEN_SAFETY_HELPER=$(quote" in text
    )
    assert "scripts/ha/patroni_role_agent.py" in text
    assert "scripts/ha/patroni_compose_runtime.py" in text
    assert "scripts/ha/patroni_role_agent_config.py" in text
    assert "scripts/ha/patroni_local_identity.py" in text
    assert "/usr/local/sbin/mvn-patroni-role-agent" in text
    assert "/usr/local/sbin/patroni_compose_runtime.py" in text
    assert "/usr/local/sbin/patroni_role_agent_config.py" in text
    assert "/usr/local/sbin/patroni_local_identity.py" in text
    transaction_runner = TRANSACTION_RUNNER.read_text(encoding="utf-8")
    role_asset_helper = (
        REPO_ROOT / "scripts/ha/patroni_role_agent_candidate_assets.sh"
    ).read_text(encoding="utf-8")
    assert "PATRONI_ROLE_IDENTITY_SOURCE" in transaction_runner
    assert "patroni_role_assets_install" in transaction_runner
    assert "systemctl restart" in role_asset_helper
    assert "systemctl is-active --quiet" in role_asset_helper
    assert 'API_DEPLOY_LOCK_FD="${DEPLOY_LOCK_FD}"' in transaction_runner
    assert "API_DEPLOY_LOCK_ALREADY_HELD=true" not in transaction_runner
    assert 'transaction cleanup' in transaction_runner
    assert 'API_COMPOSE_FILE="$(basename "${CANONICAL_FILE}")"' in transaction_runner
    assert "API_PROXY_MODE=" in text
    assert "upstream.conf" in text
    assert 'scp "${SSH_OPTS[@]}" deploy/ha/proxy/nginx.conf' not in text
    assert "up -d db" not in text
    assert "docker compose" not in text


def test_remote_orchestrator_passes_token_over_stdin_not_command_line():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "IFS= read -r GHCR_PAT" in text
    assert "IFS= read -r BOT_VOICE_TRANSCRIPTION_API_KEY" in text
    assert "export GHCR_PAT" in text
    assert "GHCR_PAT='" not in text
    assert "BOT_VOICE_TRANSCRIPTION_API_KEY='" not in text
    assert "sync_bot_voice_env.py" in text


def test_installed_role_agent_loads_its_pinned_sibling_module(tmp_path):
    target = tmp_path / "mvn-patroni-role-agent"
    identity = tmp_path / "patroni_local_identity.py"
    config = tmp_path / "patroni_role_agent_config.py"
    compose_runtime = tmp_path / "patroni_compose_runtime.py"
    shutil.copy2(REPO_ROOT / "scripts/ha/patroni_role_agent.py", target)
    shutil.copy2(REPO_ROOT / "scripts/ha/patroni_local_identity.py", identity)
    shutil.copy2(REPO_ROOT / "scripts/ha/patroni_role_agent_config.py", config)
    shutil.copy2(REPO_ROOT / "scripts/ha/patroni_compose_runtime.py", compose_runtime)

    result = subprocess.run(
        [sys.executable, "-E", str(target), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--once" in result.stdout


def test_remote_probe_normalizes_replica_to_standby(tmp_path):
    result = _run_probe(tmp_path, "replica")

    assert result.returncode == 0, result.stderr
    assert "example.invalid role=standby" in result.stdout
    assert (tmp_path / "known-hosts.capture").read_text(encoding="utf-8") == (
        "example.invalid " + API_HOST_KEY.read_text(encoding="utf-8")
    )
    ssh_args = (tmp_path / "ssh-args.log").read_text(encoding="utf-8").splitlines()
    assert "StrictHostKeyChecking=yes" in ssh_args
    assert "GlobalKnownHostsFile=/dev/null" in ssh_args
    assert "HostKeyAlgorithms=ssh-ed25519" in ssh_args
    assert "UpdateHostKeys=no" in ssh_args
    assert "IdentitiesOnly=yes" in ssh_args
    assert (tmp_path / "ssh-file-modes.capture").read_text(encoding="utf-8") == (
        "600 600"
    )


def test_remote_probe_rejects_unknown_running_role(tmp_path):
    result = _run_probe(tmp_path, "mystery")

    assert result.returncode != 0
    assert "role=standby" not in result.stdout


def test_remote_probe_refuses_active_pitr_maintenance_before_role_lookup(tmp_path):
    marker = tmp_path / "maintenance"
    marker.write_text("owned\n", encoding="utf-8")

    result = _run_probe(tmp_path, "primary", maintenance_marker=marker)

    assert result.returncode != 0
    assert "PITR release maintenance is active" in result.stderr
    assert "role=primary" not in result.stdout


def test_tracked_patroni_host_keys_have_reviewed_ed25519_fingerprints():
    for path, expected_fingerprint in EXPECTED_HOST_KEY_FINGERPRINTS.items():
        assert _ed25519_sha256_fingerprint(path) == expected_fingerprint


def test_remote_probe_rejects_invalid_pinned_host_key_before_ssh(tmp_path):
    invalid_key = tmp_path / "invalid-host-key.pub"
    invalid_key.write_text("ssh-ed25519 not-base64\n", encoding="utf-8")

    result = _run_probe(tmp_path, "replica", host_key_source=invalid_key)

    assert result.returncode != 0
    assert "pinned SSH host key" in result.stdout


def test_remote_probe_rejects_invalid_ed25519_wire_blob(tmp_path):
    invalid_key = tmp_path / "invalid-wire-host-key.pub"
    invalid_key.write_text("ssh-ed25519 QUFBQQ==\n", encoding="utf-8")

    result = _run_probe(tmp_path, "replica", host_key_source=invalid_key)

    assert result.returncode != 0
    assert "pinned SSH host key is invalid" in result.stdout


def test_remote_probe_rejects_multiline_pinned_host_key_before_ssh(tmp_path):
    multiline_key = tmp_path / "multiline-host-key.pub"
    multiline_key.write_text(
        API_HOST_KEY.read_text(encoding="utf-8")
        + RESERVE_HOST_KEY.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = _run_probe(tmp_path, "replica", host_key_source=multiline_key)

    assert result.returncode != 0
    assert "exactly one line" in result.stdout


def test_remote_probe_requires_regular_non_symlink_host_key_source(tmp_path):
    missing = tmp_path / "missing-host-key.pub"
    missing_result = _run_probe(tmp_path, "replica", host_key_source=missing)

    symlink = tmp_path / "host-key-link.pub"
    symlink.symlink_to(API_HOST_KEY)
    symlink_result = _run_probe(tmp_path, "replica", host_key_source=symlink)

    assert missing_result.returncode != 0
    assert symlink_result.returncode != 0
    assert "tracked API_NODE_SSH_HOST_KEY_SOURCE is required" in missing_result.stdout
    assert "tracked API_NODE_SSH_HOST_KEY_SOURCE is required" in symlink_result.stdout


def test_remote_probe_rejects_unsafe_host_and_user_before_ssh(tmp_path):
    unsafe_host = _run_probe(
        tmp_path,
        "replica",
        node_host="example.invalid -oProxyCommand=evil",
    )

    other_tmp_path = tmp_path / "unsafe-user"
    other_tmp_path.mkdir()
    unsafe_user = _run_probe(
        other_tmp_path,
        "replica",
        node_user="-oProxyCommand=evil",
    )

    assert unsafe_host.returncode != 0
    assert "API_NODE_HOST contains unsupported characters" in unsafe_host.stdout
    assert unsafe_user.returncode != 0
    assert "API_NODE_USER contains unsupported characters" in unsafe_user.stdout


def test_patroni_workflow_pins_every_remote_invocation_to_physical_node_key():
    workflow = (
        REPO_ROOT / ".github/workflows/deploy-api-patroni.yml"
    ).read_text(encoding="utf-8")

    assert workflow.count("run: bash scripts/ha/run_patroni_node_remote.sh") == 8
    assert workflow.count("API_NODE_SSH_HOST_KEY_SOURCE:") == 8
    assert workflow.count("mvn-api-ssh-host-key.pub") == 4
    assert workflow.count("zakup-ssh-host-key.pub") == 4
    assert workflow.count("vars.PATRONI_MVN_API_HOST") == 4
    assert workflow.count("vars.PATRONI_ZAKUP_HOST") == 4
    assert "vars.API_NODE_HOST" not in workflow
    assert "secrets.SSH_HOST_API" not in workflow
    assert "vars.API_STANDBY_HOST" not in workflow

    expected_jobs = {
        "mvn-api-ssh-host-key.pub": (
            "probe-api-node",
            "migrate-api-node",
            "deploy-replica-api",
            "deploy-primary-api",
        ),
        "zakup-ssh-host-key.pub": (
            "probe-reserve-node",
            "migrate-reserve-node",
            "deploy-replica-reserve",
            "deploy-primary-reserve",
        ),
    }
    for expected_key, job_names in expected_jobs.items():
        for job_name in job_names:
            job = _workflow_job_block(workflow, job_name)
            assert job.count("API_NODE_SSH_HOST_KEY_SOURCE:") == 1
            assert expected_key in job
