from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ha/run_patroni_node_remote.sh"


def test_remote_orchestrator_has_strict_operations_and_never_manages_database():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "probe|migrate|deploy" in text
    assert "StrictHostKeyChecking=yes" in text
    assert "UserKnownHostsFile=" in text
    assert "docker-compose.patroni.yml" in text
    assert "run_patroni_migrations.sh" in text
    assert "deploy_patroni_api_node.sh" in text
    assert "deploy_backend_blue_green.sh" in text
    assert "scripts/ha/patroni_role_agent.py" in text
    assert "/usr/local/sbin/mvn-patroni-role-agent" in text
    assert "systemctl restart" in text
    assert "systemctl is-active --quiet" in text
    assert "API_PROXY_MODE=" in text
    assert "upstream.conf" in text
    assert "up -d db" not in text
    assert "docker compose" not in text


def test_remote_orchestrator_passes_token_over_stdin_not_command_line():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "IFS= read -r GHCR_PAT" in text
    assert "export GHCR_PAT" in text
    assert "GHCR_PAT='" not in text
