import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/ha/switch_github_api_primary.py"


spec = importlib.util.spec_from_file_location("switch_github_api_primary", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeCompleted:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_build_routing_for_normal_mvn_api_primary():
    ssh_host, variables = module.build_routing("mvn-api")

    assert ssh_host == "185.250.45.54"
    assert variables["API_PRIMARY_ORIGIN"] == "185.250.45.54"
    assert variables["API_STANDBY_ORIGIN"] == "193.47.42.213"
    assert variables["API_PROJECT_DIR"] == "/opt/air-api"
    assert variables["API_COMPOSE_FILE"] == "docker-compose.prod.yml"
    assert variables["API_COMPOSE_SOURCE_FILE"] == "deploy/ha/mvn-api/docker-compose.primary.yml"
    assert variables["API_BASE_URL"] == "http://localhost:18080"
    assert variables["API_READY_URL"] == "http://localhost:18080/api/ready"
    assert variables["API_TUNNEL_REMOTE_PORT"] == "18080"
    assert variables["API_DEPLOY_STRATEGY"] == "blue_green"
    assert variables["API_STANDBY_HOST"] == "193.47.42.213"
    assert variables["API_STANDBY_PROJECT_DIR"] == "/opt/mvn-reserve"
    assert variables["API_STANDBY_COMPOSE_SOURCE_FILE"] == "deploy/ha/zakup/docker-compose.standby.yml"
    assert variables["API_STANDBY_HEALTH_URL"] == "http://localhost:18000/api/health"
    assert variables["API_COPY_COMPOSE"] == "true"
    assert variables["API_STANDBY_COPY_COMPOSE"] == "true"
    assert variables["PATRONI_MVN_API_HOST"] == "185.250.45.54"
    assert variables["PATRONI_ZAKUP_HOST"] == "193.47.42.213"


def test_build_routing_for_promoted_zakup_primary():
    ssh_host, variables = module.build_routing("zakup")

    assert ssh_host == "193.47.42.213"
    assert variables["API_PRIMARY_ORIGIN"] == "193.47.42.213"
    assert variables["API_STANDBY_ORIGIN"] == "185.250.45.54"
    assert variables["API_PROJECT_DIR"] == "/opt/mvn-reserve"
    assert variables["API_COMPOSE_FILE"] == "docker-compose.reserve.yml"
    assert variables["API_COMPOSE_SOURCE_FILE"] == "deploy/ha/zakup/docker-compose.primary.yml"
    assert variables["API_BASE_URL"] == "http://localhost:18000"
    assert variables["API_READY_URL"] == "http://localhost:18000/api/ready"
    assert variables["API_TUNNEL_REMOTE_PORT"] == "18000"
    assert variables["API_DEPLOY_STRATEGY"] == "in_place"
    assert variables["API_STANDBY_HOST"] == "185.250.45.54"
    assert variables["API_STANDBY_PROJECT_DIR"] == "/opt/air-api"
    assert variables["API_STANDBY_COMPOSE_SOURCE_FILE"] == "deploy/ha/mvn-api/docker-compose.standby.yml"
    assert variables["API_STANDBY_HEALTH_URL"] == "http://localhost:8000/api/health"
    assert variables["PATRONI_MVN_API_HOST"] == "185.250.45.54"
    assert variables["PATRONI_ZAKUP_HOST"] == "193.47.42.213"


def test_dry_run_prints_plan_without_writes(monkeypatch, capsys):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api", "--primary", "zakup"]) == 0

    assert calls == []
    output = capsys.readouterr().out
    assert "primary=zakup standby=mvn-api" in output
    assert "secret SSH_HOST_API=193.47.42.213" in output
    assert "variable API_COMPOSE_SOURCE_FILE=deploy/ha/zakup/docker-compose.primary.yml" in output
    assert "no changes applied" in output


def test_confirm_sets_secret_then_variables_without_values_in_args(monkeypatch):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api", "--primary", "zakup", "--confirm"]) == 0

    secret_call = calls[0]
    assert secret_call == (
        ["gh", "secret", "set", "SSH_HOST_API", "--repo", "mvnby/air-api"],
        "193.47.42.213\n",
    )
    variable_calls = [call for call in calls if call[0][:3] == ["gh", "variable", "set"]]
    variable_names = [args[3] for args, _stdin in variable_calls]

    assert "API_PROJECT_DIR" in variable_names
    assert "API_STANDBY_HOST" in variable_names
    assert "API_PRIMARY_ORIGIN" in variable_names
    assert "PATRONI_MVN_API_HOST" in variable_names
    assert "PATRONI_ZAKUP_HOST" in variable_names
    assert all("193.47.42.213" not in args for args, _stdin in calls)
    assert any(args[3] == "API_PROJECT_DIR" and stdin == "/opt/mvn-reserve\n" for args, stdin in variable_calls)


def test_confirm_stops_on_secret_write_failure(monkeypatch):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        if list(args[:3]) == ["gh", "secret", "set"]:
            return FakeCompleted(stderr="denied", returncode=1)
        return FakeCompleted()

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api", "--primary", "mvn-api", "--confirm"]) == 1

    assert len(calls) == 1
