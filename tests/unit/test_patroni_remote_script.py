import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ha/run_patroni_node_remote.sh"
TRANSACTION_RUNNER = REPO_ROOT / "scripts/ha/run_patroni_candidate_transaction.sh"


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_probe(tmp_path: Path, role: str) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(
        fake_bin / "ssh-keyscan",
        "#!/usr/bin/env bash\nprintf 'example.invalid ssh-ed25519 AAAATEST\\n'\n",
    )
    _executable(
        fake_bin / "ssh",
        '#!/usr/bin/env bash\nremote_command="${!#}"\nbash -c "${remote_command}"\n',
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
            "API_NODE_HOST": "example.invalid",
            "API_NODE_USER": "deploy",
            "SSH_PRIVATE_KEY": "test-private-key",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_RUN_ID": "test-run",
            "GITHUB_JOB": "probe",
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_remote_orchestrator_has_strict_operations_and_never_manages_database():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "probe|migrate|deploy" in text
    assert "required_commands=(ssh ssh-keyscan)" in text
    assert 'required_commands+=(scp)' in text
    assert "StrictHostKeyChecking=yes" in text
    assert "UserKnownHostsFile=" in text
    assert "docker-compose.patroni.yml" in text
    assert "run_patroni_migrations.sh" in text
    assert "deploy_patroni_api_node.sh" in text
    assert "deploy_backend_blue_green.sh" in text
    assert "deploy_backend_blue_green_safety.sh" in text
    assert "prepare_google_oauth_token_dir.sh" in text
    assert 'candidate_id="$(printf' in text
    assert 'REMOTE_COMPOSE_FILE="docker-compose.patroni.candidate.${candidate_id}.yml"' in text
    assert "run_patroni_candidate_transaction.sh" in text
    assert "compose_candidate_transaction.sh" in text
    assert "reconcile_backend_compose_runtime.sh" in text
    assert (
        "API_BLUE_GREEN_SAFETY_HELPER=/tmp/deploy_backend_blue_green_safety.sh" in text
    )
    assert "scripts/ha/patroni_role_agent.py" in text
    assert "/usr/local/sbin/mvn-patroni-role-agent" in text
    transaction_runner = TRANSACTION_RUNNER.read_text(encoding="utf-8")
    assert "systemctl restart" in transaction_runner
    assert "systemctl is-active --quiet" in transaction_runner
    assert "API_DEPLOY_LOCK_ALREADY_HELD=true" in transaction_runner
    assert 'transaction cleanup' in transaction_runner
    assert 'API_COMPOSE_FILE="$(basename "${CANONICAL_FILE}")"' in transaction_runner
    assert "API_PROXY_MODE=" in text
    assert "upstream.conf" in text
    assert "up -d db" not in text
    assert "docker compose" not in text


def test_remote_orchestrator_passes_token_over_stdin_not_command_line():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "IFS= read -r GHCR_PAT" in text
    assert "export GHCR_PAT" in text
    assert "GHCR_PAT='" not in text


def test_remote_probe_normalizes_replica_to_standby(tmp_path):
    result = _run_probe(tmp_path, "replica")

    assert result.returncode == 0, result.stderr
    assert "example.invalid role=standby" in result.stdout


def test_remote_probe_rejects_unknown_running_role(tmp_path):
    result = _run_probe(tmp_path, "mystery")

    assert result.returncode != 0
    assert "role=standby" not in result.stdout
