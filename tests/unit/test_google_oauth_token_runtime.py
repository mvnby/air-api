import importlib.util
import json
import os
import re
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PREPARE_SCRIPT = REPO_ROOT / "scripts/prepare_google_oauth_token_dir.sh"
PRODUCTION_COMPOSE_FILES = (
    "docker-compose.prod.yml",
    "deploy/ha/mvn-api/docker-compose.primary.yml",
    "deploy/ha/mvn-api/docker-compose.standby.yml",
    "deploy/ha/mvn-api/docker-compose.patroni.yml",
    "deploy/ha/zakup/docker-compose.primary.yml",
    "deploy/ha/zakup/docker-compose.standby.yml",
    "deploy/ha/zakup/docker-compose.patroni.yml",
)


def _token_payload(marker: str = "secret-marker") -> str:
    return json.dumps(
        {
            "token": marker,
            "refresh_token": f"refresh-{marker}",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client-id",
            "client_secret": "client-secret",
        }
    )


def _run_prepare(project: Path, *arguments: str, **extra_env: str):
    return subprocess.run(
        ["bash", str(PREPARE_SCRIPT), *arguments],
        env={
            **os.environ,
            "GOOGLE_OAUTH_PROJECT_DIR": str(project),
            **extra_env,
        },
        text=True,
        capture_output=True,
        check=False,
    )


def _load_script_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_production_ha_composes_use_writable_oauth_directory_contract():
    assert len(PRODUCTION_COMPOSE_FILES) == 7
    forbidden = re.compile(r"token\.json\s*:\s*/app/token\.json")

    for relative_path in PRODUCTION_COMPOSE_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "GOOGLE_TOKEN_FILE: /app/google-oauth/token.json" in text
        assert "./google-oauth:/app/google-oauth" in text
        assert "/app/client_secret.json:ro" in text
        assert "/app/credentials.json:ro" in text
        assert "/app/token.json" not in text
        assert not forbidden.search(text)


def test_no_repo_compose_reintroduces_single_file_oauth_token_mount():
    forbidden = re.compile(r"token\.json\s*:\s*/app/token\.json")
    compose_files = tuple(REPO_ROOT.rglob("docker-compose*.yml"))
    assert compose_files
    for path in compose_files:
        assert not forbidden.search(path.read_text(encoding="utf-8")), path


def test_prepare_migrates_legacy_token_atomically_and_retains_source(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    legacy = project / "token.json"
    legacy.write_text(_token_payload(), encoding="utf-8")
    legacy.chmod(0o644)

    result = _run_prepare(project, "prepare")

    assert result.returncode == 0, result.stderr
    destination = project / "google-oauth/token.json"
    assert destination.read_text(encoding="utf-8") == legacy.read_text(encoding="utf-8")
    assert legacy.exists()
    assert stat.S_IMODE(legacy.stat().st_mode) == 0o600
    assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert "secret-marker" not in result.stdout + result.stderr
    assert list(destination.parent.glob(".token.json.migrate.*")) == []
    assert _run_prepare(project, "verify").returncode == 0

    script = PREPARE_SCRIPT.read_text(encoding="utf-8")
    assert 'fsync_path "${temporary}"' in script
    assert 'fsync_path "${TOKEN_DIR}"' in script


def test_prepare_supports_reserve_secrets_layout_without_deleting_legacy(tmp_path):
    project = tmp_path / "reserve"
    legacy = project / "secrets/token.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(_token_payload("reserve"), encoding="utf-8")

    result = _run_prepare(project, "prepare")

    assert result.returncode == 0, result.stderr
    assert (project / "google-oauth/token.json").is_file()
    assert legacy.is_file()


def test_prepare_rejects_ambiguous_or_invalid_legacy_tokens(tmp_path):
    project = tmp_path / "project"
    (project / "secrets").mkdir(parents=True)
    (project / "token.json").write_text(_token_payload("one"), encoding="utf-8")
    (project / "secrets/token.json").write_text(
        _token_payload("two"), encoding="utf-8"
    )

    ambiguous = _run_prepare(project, "prepare")
    assert ambiguous.returncode != 0
    assert "multiple different legacy tokens" in ambiguous.stderr
    assert not (project / "google-oauth/token.json").exists()

    (project / "secrets/token.json").unlink()
    (project / "token.json").write_text("{}", encoding="utf-8")
    invalid = _run_prepare(project, "prepare")
    assert invalid.returncode != 0
    assert "missing required fields" in invalid.stderr


def test_prepare_requires_complete_refresh_credentials(tmp_path):
    required_fields = ("refresh_token", "client_id", "client_secret", "token_uri")
    for field in required_fields:
        project = tmp_path / field
        project.mkdir()
        payload = json.loads(_token_payload(field))
        payload.pop(field)
        (project / "token.json").write_text(json.dumps(payload), encoding="utf-8")

        result = _run_prepare(project, "prepare")

        assert result.returncode != 0
        assert f"missing required fields: {field}" in result.stderr
        assert not (project / "google-oauth/token.json").exists()


def test_legacy_python_consumers_honor_configured_token_path(tmp_path, monkeypatch):
    restore_db = _load_script_module("restore_db_token_test", "scripts/restore_db.py")
    get_token = _load_script_module("get_token_path_test", "scripts/get_token.py")
    token_file = tmp_path / "oauth/token.json"
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(token_file))

    class Credentials:
        refresh_token = "refresh-token"
        client_id = "client-id"
        client_secret = "client-secret"
        token_uri = "https://oauth2.googleapis.com/token"

        @staticmethod
        def to_json():
            return _token_payload("python-consumer")

    assert restore_db.get_token_file() == token_file
    assert get_token.get_token_file() == token_file
    restore_db.persist_credentials(Credentials(), token_file)
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert list(token_file.parent.glob(".token.json.*")) == []

    generated_token = tmp_path / "generated-oauth/token.json"
    get_token.persist_token(Credentials(), generated_token)
    assert stat.S_IMODE(generated_token.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(generated_token.stat().st_mode) == 0o600
    assert list(generated_token.parent.glob(".token.json.*")) == []


def test_get_token_does_not_chmod_an_existing_parent_directory(tmp_path):
    get_token = _load_script_module("get_token_mode_test", "scripts/get_token.py")
    existing_parent = tmp_path / "shared"
    existing_parent.mkdir()
    existing_parent.chmod(0o755)

    class Credentials:
        refresh_token = "refresh-token"
        client_id = "client-id"
        client_secret = "client-secret"
        token_uri = "https://oauth2.googleapis.com/token"

        @staticmethod
        def to_json():
            return _token_payload("existing-parent")

    get_token.persist_token(Credentials(), existing_parent / "token.json")

    assert stat.S_IMODE(existing_parent.stat().st_mode) == 0o755
    assert stat.S_IMODE((existing_parent / "token.json").stat().st_mode) == 0o600


def test_deploy_paths_run_token_preparation_before_compose_activation():
    scripts = (
        "scripts/deploy.sh",
        "scripts/deploy_backend_blue_green.sh",
        "scripts/ha/run_patroni_migrations.sh",
        "scripts/ha/deploy_patroni_api_node.sh",
    )
    for relative_path in scripts:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT" in text
        assert 'bash "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" prepare' in text

    remote = (REPO_ROOT / "scripts/ha/run_patroni_node_remote.sh").read_text(
        encoding="utf-8"
    )
    assert "scripts/prepare_google_oauth_token_dir.sh" in remote
    assert "GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT=/tmp/prepare_google_oauth_token_dir.sh" in remote
    assert 'candidate_id="$(printf' in remote
    assert 'REMOTE_COMPOSE_FILE="docker-compose.patroni.candidate.${candidate_id}.yml"' in remote
    assert "run_patroni_candidate_transaction.sh" in remote
    assert "compose_candidate_transaction.sh" in remote

    workflows = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in (
            ".github/workflows/deploy.yml",
            ".github/workflows/deploy-api-standby.yml",
        )
    )
    assert "scripts/prepare_google_oauth_token_dir.sh" in workflows
    assert "deploy_backend_candidate_transaction.sh" in workflows
    assert ".candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" in workflows

    legacy_deploy = (REPO_ROOT / "deploy_api.sh").read_text(encoding="utf-8")
    assert "is retired" in legacy_deploy
    assert "GitHub Actions image workflow" in legacy_deploy
