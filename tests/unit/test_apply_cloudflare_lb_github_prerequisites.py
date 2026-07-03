import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/ha/apply_cloudflare_lb_github_prerequisites.py"


spec = importlib.util.spec_from_file_location("apply_cloudflare_lb_github_prerequisites", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeCompleted:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_set_secret_uses_stdin_not_command_args():
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    module.set_secret("mvnby/air-api", "CLOUDFLARE_LB_READ_TOKEN", "super-secret", runner=fake_runner)

    args, stdin = calls[0]
    assert args == ["gh", "secret", "set", "CLOUDFLARE_LB_READ_TOKEN", "--repo", "mvnby/air-api"]
    assert stdin == "super-secret\n"
    assert "super-secret" not in args


def test_set_variable_uses_stdin():
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    module.set_variable("mvnby/air-api", "CLOUDFLARE_ZONE_ID", "zone-id", runner=fake_runner)

    assert calls == [(["gh", "variable", "set", "CLOUDFLARE_ZONE_ID", "--repo", "mvnby/air-api"], "zone-id\n")]


def test_parse_run_id_from_workflow_url():
    assert (
        module.parse_run_id("https://github.com/mvnby/air-api/actions/runs/28636799268")
        == "28636799268"
    )


def test_collect_inputs_reports_missing_env_names_without_values(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_LB_READ_TOKEN", "token")
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

    try:
        module.collect_inputs(
            token_env="CLOUDFLARE_LB_READ_TOKEN",
            zone_id_env="CLOUDFLARE_ZONE_ID",
            account_id_env="CLOUDFLARE_ACCOUNT_ID",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("collect_inputs should fail")

    assert "CLOUDFLARE_ZONE_ID" in message
    assert "CLOUDFLARE_ACCOUNT_ID" in message
    assert "token" not in message


def test_main_rejects_mark_required_without_wait_before_writes(monkeypatch, capsys):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    monkeypatch.setenv("CLOUDFLARE_LB_READ_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "zone")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api", "--mark-required", "--no-wait"]) == 1

    assert calls == []
    assert "--mark-required requires waiting" in capsys.readouterr().out


def test_main_sets_metadata_then_runs_required_audit(monkeypatch):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        if list(args[:3]) == ["gh", "workflow", "run"]:
            return FakeCompleted(stdout="https://github.com/mvnby/air-api/actions/runs/28636799268\n")
        return FakeCompleted()

    monkeypatch.setenv("CLOUDFLARE_LB_READ_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "zone")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api"]) == 0

    command_names = [call[0][:3] for call in calls]
    assert ["gh", "secret", "set"] in command_names
    assert ["gh", "variable", "set"] in command_names
    assert ["gh", "workflow", "run"] in command_names
    assert ["gh", "run", "watch"] in command_names
    assert all("token" not in args for args, _stdin in calls)
