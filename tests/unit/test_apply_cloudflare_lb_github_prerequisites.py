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


def test_load_env_file_sets_missing_values_without_overriding(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "CLOUDFLARE_API_TOKEN_LB_AUDIT=from-file",
                "CLOUDFLARE_ACCOUNT_ID='account-from-file'",
                "CLOUDFLARE_ZONE_ID=zone-from-file # comment",
                "GH_TOKEN=stale-github-token",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "existing-account")
    monkeypatch.delenv("GH_TOKEN", raising=False)

    module.load_env_file(
        env_file,
        allowed_names={"CLOUDFLARE_API_TOKEN_LB_AUDIT", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ZONE_ID"},
    )

    assert module.env_value("CLOUDFLARE_API_TOKEN_LB_AUDIT") == "from-file"
    assert module.env_value("CLOUDFLARE_ACCOUNT_ID") == "existing-account"
    assert module.env_value("CLOUDFLARE_ZONE_ID") == "zone-from-file"
    assert module.env_value("GH_TOKEN") == ""


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


def test_collect_inputs_accepts_audit_token_alias(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_LB_READ_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN_LB_AUDIT", "audit-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "zone")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")

    token, zone_id, account_id, token_source = module.collect_inputs(
        token_env="CLOUDFLARE_LB_READ_TOKEN",
        zone_id_env="CLOUDFLARE_ZONE_ID",
        account_id_env="CLOUDFLARE_ACCOUNT_ID",
    )

    assert token == "audit-token"
    assert token_source == "CLOUDFLARE_API_TOKEN_LB_AUDIT"
    assert zone_id == "zone"
    assert account_id == "account"


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


def test_main_writes_canonical_secret_from_audit_token_alias(monkeypatch):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        if list(args[:3]) == ["gh", "workflow", "run"]:
            return FakeCompleted(stdout="https://github.com/mvnby/air-api/actions/runs/28636799268\n")
        return FakeCompleted()

    monkeypatch.delenv("CLOUDFLARE_LB_READ_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN_LB_AUDIT", "audit-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "zone")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api"]) == 0

    assert (
        ["gh", "secret", "set", "CLOUDFLARE_LB_READ_TOKEN", "--repo", "mvnby/air-api"],
        "audit-token\n",
    ) in calls
    assert all("audit-token" not in args for args, _stdin in calls)


def test_main_can_load_project_env_file(tmp_path, monkeypatch):
    calls = []
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "CLOUDFLARE_API_TOKEN_LB_AUDIT=audit-token",
                "CLOUDFLARE_ZONE_ID=zone",
                "CLOUDFLARE_ACCOUNT_ID=account",
            ]
        ),
        encoding="utf-8",
    )

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        if list(args[:3]) == ["gh", "workflow", "run"]:
            return FakeCompleted(stdout="https://github.com/mvnby/air-api/actions/runs/28636799268\n")
        return FakeCompleted()

    monkeypatch.delenv("CLOUDFLARE_API_TOKEN_LB_AUDIT", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--repo", "mvnby/air-api", "--env-file", str(env_file)]) == 0

    assert (
        ["gh", "secret", "set", "CLOUDFLARE_LB_READ_TOKEN", "--repo", "mvnby/air-api"],
        "audit-token\n",
    ) in calls


def test_workflow_output_without_url_falls_back_to_recent_run_list(monkeypatch):
    calls = []
    real_datetime = module.datetime

    def fake_runner(args, stdin):
        args = list(args)
        calls.append((args, stdin))
        if args[:3] == ["gh", "workflow", "run"]:
            return FakeCompleted(stdout="Created workflow_dispatch event\n")
        if args[:3] == ["gh", "run", "list"]:
            return FakeCompleted(
                stdout='[{"databaseId":28639999999,"createdAt":"2026-07-03T05:08:21Z",'
                '"url":"https://github.com/mvnby/air-api/actions/runs/28639999999"}]'
            )
        return FakeCompleted()

    class FrozenDatetime:
        @staticmethod
        def now(_tz):
            return real_datetime(2026, 7, 3, 5, 8, 22, tzinfo=module.timezone.utc)

        @staticmethod
        def fromisoformat(value):
            return real_datetime.fromisoformat(value)

    monkeypatch.setattr(module, "_run_subprocess", fake_runner)
    monkeypatch.setattr(module, "datetime", FrozenDatetime)

    run_id = module.run_cloudflare_required_workflow(
        repo="mvnby/air-api",
        ref="main",
        wait=True,
    )

    assert run_id == "28639999999"
    assert any(args[:3] == ["gh", "run", "list"] for args, _stdin in calls)
    assert any(args[:3] == ["gh", "run", "watch"] and args[3] == "28639999999" for args, _stdin in calls)
