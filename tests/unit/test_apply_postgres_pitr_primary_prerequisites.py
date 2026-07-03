import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/ha/apply_postgres_pitr_primary_prerequisites.py"


spec = importlib.util.spec_from_file_location("apply_postgres_pitr_primary_prerequisites", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeCompleted:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _env(**overrides):
    values = {
        "POSTGRES_PITR_CLUSTER": "mvn-api",
        "POSTGRES_PITR_S3_BUCKET": "mvn-postgres-pitr",
        "POSTGRES_PITR_S3_ENDPOINT_URL": "https://account-id.r2.cloudflarestorage.com",
        "POSTGRES_PITR_S3_REGION": "auto",
        "POSTGRES_PITR_S3_ACCESS_KEY_ID": "access-key-id",
        "POSTGRES_PITR_S3_SECRET_ACCESS_KEY": "super-secret-key",
        "POSTGRES_PITR_S3_KEY_PREFIX": "postgres/pitr",
    }
    values.update(overrides)
    return values


def test_render_env_redacts_access_keys():
    config = module.collect_inputs(environ=_env(), no_prompt=True)

    rendered = module.render_env(config, redact=True)

    assert "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr" in rendered
    assert "access-key-id" not in rendered
    assert "super-secret-key" not in rendered
    assert "POSTGRES_PITR_S3_ACCESS_KEY_ID=redacted" in rendered
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=redacted" in rendered


def test_load_env_file_loads_only_pitr_keys_without_overriding(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr",
                "POSTGRES_PITR_S3_ENDPOINT_URL='https://account-id.r2.cloudflarestorage.com'",
                "POSTGRES_PITR_S3_ACCESS_KEY_ID=access-key-id",
                "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key",
                "GH_TOKEN=stale-github-token",
                "CLOUDFLARE_API_TOKEN_LB_AUDIT=cloudflare-token",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("POSTGRES_PITR_S3_BUCKET", "existing-bucket")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN_LB_AUDIT", raising=False)

    module.load_env_file(env_file)

    assert module._env("POSTGRES_PITR_S3_BUCKET", module.os.environ) == "existing-bucket"
    assert (
        module._env("POSTGRES_PITR_S3_ENDPOINT_URL", module.os.environ)
        == "https://account-id.r2.cloudflarestorage.com"
    )
    assert module._env("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", module.os.environ) == "super-secret-key"
    assert module._env("GH_TOKEN", module.os.environ) == ""
    assert module._env("CLOUDFLARE_API_TOKEN_LB_AUDIT", module.os.environ) == ""


def test_upload_remote_env_passes_secret_only_via_stdin():
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    config = module.collect_inputs(environ=_env(), no_prompt=True)
    env_text = module.render_env(config)

    module.upload_remote_env(
        ssh_host="mvn-api",
        remote_env_file="/root/mvn-postgres-pitr.env",
        env_text=env_text,
        runner=fake_runner,
    )

    args, stdin = calls[0]
    assert args == [
        "ssh",
        "mvn-api",
        "umask 077; cat > /root/mvn-postgres-pitr.env; chmod 600 /root/mvn-postgres-pitr.env",
    ]
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key" in stdin
    assert all("super-secret-key" not in arg for arg in args)


def test_run_remote_phase_removes_temporary_env_file():
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    module.run_remote_phase(
        ssh_host="mvn-api",
        remote_env_file="/root/mvn-postgres-pitr.env",
        bootstrap_helper="/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        project_dir="/opt/air-api",
        compose_file="docker-compose.prod.yml",
        phase="preflight",
        runner=fake_runner,
    )

    args, stdin = calls[0]
    assert stdin is None
    assert args[:2] == ["ssh", "mvn-api"]
    assert "ENV_INPUT_FILE=/root/mvn-postgres-pitr.env" in args[2]
    assert "rm -f /root/mvn-postgres-pitr.env" in args[2]
    assert "/usr/local/sbin/mvn-postgres-pitr-bootstrap preflight" in args[2]


def test_collect_inputs_reports_missing_names_without_secret_values():
    try:
        module.collect_inputs(
            environ=_env(POSTGRES_PITR_S3_BUCKET="", POSTGRES_PITR_S3_SECRET_ACCESS_KEY="super-secret-key"),
            no_prompt=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("collect_inputs should fail")

    assert "POSTGRES_PITR_S3_BUCKET" in message
    assert "super-secret-key" not in message


def test_collect_inputs_rejects_public_endpoint():
    try:
        module.collect_inputs(
            environ=_env(POSTGRES_PITR_S3_ENDPOINT_URL="https://cdn.mvn.by"),
            no_prompt=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("collect_inputs should fail")

    assert "r2.cloudflarestorage.com" in message
    assert "super-secret-key" not in message


def test_dry_run_prints_redacted_env(monkeypatch, capsys):
    monkeypatch.setenv("POSTGRES_PITR_CLUSTER", "mvn-api")
    monkeypatch.setenv("POSTGRES_PITR_S3_BUCKET", "mvn-postgres-pitr")
    monkeypatch.setenv("POSTGRES_PITR_S3_ENDPOINT_URL", "https://account-id.r2.cloudflarestorage.com")
    monkeypatch.setenv("POSTGRES_PITR_S3_REGION", "auto")
    monkeypatch.setenv("POSTGRES_PITR_S3_ACCESS_KEY_ID", "access-key-id")
    monkeypatch.setenv("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", "super-secret-key")
    monkeypatch.setenv("POSTGRES_PITR_S3_KEY_PREFIX", "postgres/pitr")

    assert module.main(["--dry-run", "--no-prompt"]) == 0

    output = capsys.readouterr().out
    assert "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr" in output
    assert "access-key-id" not in output
    assert "super-secret-key" not in output
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=redacted" in output


def test_main_runs_upload_and_preflight_with_monkeypatched_subprocess(monkeypatch):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    for name, value in _env().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--no-prompt", "--phase", "preflight"]) == 0

    assert len(calls) == 2
    assert calls[0][0][:2] == ["ssh", "mvn-api"]
    assert "super-secret-key" in calls[0][1]
    assert all("super-secret-key" not in arg for args, _stdin in calls for arg in args)
    assert "preflight" in calls[1][0][2]


def test_main_can_load_project_env_file(tmp_path, monkeypatch):
    calls = []
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(f"{name}={value}" for name, value in _env().items()),
        encoding="utf-8",
    )

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    for name in _env():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--no-prompt", "--phase", "preflight", "--env-file", str(env_file)]) == 0

    assert len(calls) == 2
    assert "super-secret-key" in calls[0][1]
    assert all("super-secret-key" not in arg for args, _stdin in calls for arg in args)
