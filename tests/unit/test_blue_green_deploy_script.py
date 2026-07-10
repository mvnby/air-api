import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/deploy_backend_blue_green.sh"
OLD_IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "1" * 64
NEW_IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "2" * 64


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
    (project / ".env").write_text(
        f"POSTGRES_USER=postgres\nPOSTGRES_PASSWORD=test\nPOSTGRES_DB=test\nBACKEND_IMAGE={OLD_IMAGE}\n",
        encoding="utf-8",
    )

    nginx_dir = tmp_path / "nginx"
    site = nginx_dir / "sites-available/air-api"
    site.parent.mkdir(parents=True)
    site.write_text(
        "server {\n    location / {\n        proxy_pass http://127.0.0.1:8000;\n    }\n}\n",
        encoding="utf-8",
    )
    upstream = nginx_dir / "snippets/mvn-api-upstream.conf"

    command_log = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _executable(fake_bin / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -u
printf 'docker %s\n' "$*" >> "$COMMAND_LOG"
if [[ "$*" == *"ps --status running --services"* ]]; then
  printf 'app\napp-blue\napp-green\nbot\napi-proxy\n'
fi
exit 0
""",
    )
    _executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
set -u
url="${*: -1}"
printf 'curl %s\n' "$*" >> "$COMMAND_LOG"
if [[ "${FAIL_CANDIDATE_READY:-false}" == "true" && "$url" == *":18001/api/ready"* ]]; then
  exit 22
fi
case "$url" in
  */api/ready)
    printf '{"status":"ok","api":"ready","database":"online","database_writable":true}\n'
    ;;
  */api/health)
    printf '{"status":"ok","database":"online"}\n'
    ;;
  *products*)
    printf '{"items":[]}\n'
    ;;
  *filters/config*)
    printf '{"price":{},"area":{},"brands":[],"expert_tags":[]}\n'
    ;;
  *)
    exit 22
    ;;
esac
""",
    )
    _executable(
        fake_bin / "nginx",
        "#!/usr/bin/env bash\nprintf 'nginx %s\n' \"$*\" >> \"$COMMAND_LOG\"\nexit 0\n",
    )
    _executable(
        fake_bin / "systemctl",
        "#!/usr/bin/env bash\nprintf 'systemctl %s\n' \"$*\" >> \"$COMMAND_LOG\"\nexit 0\n",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "API_PROJECT_DIR": str(project),
            "API_COMPOSE_FILE": "docker-compose.prod.yml",
            "API_NGINX_SITE_FILE": str(site),
            "API_NGINX_UPSTREAM_FILE": str(upstream),
            "API_NGINX_INTERNAL_FILE": str(nginx_dir / "conf.d/mvn-api-internal.conf"),
            "API_BLUE_GREEN_SUMMARY_FILE": str(tmp_path / "summary.txt"),
            "API_HEALTH_ATTEMPTS": "2",
            "API_HEALTH_DELAY_SECONDS": "0",
            "API_DRAIN_SECONDS": "0",
            "BACKEND_IMAGE": NEW_IMAGE,
            "GHCR_PAT": "test-token",
            "GITHUB_ACTOR": "test-user",
        }
    )
    return env, project, site, command_log


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_first_deploy_activates_blue_without_touching_database(tmp_path):
    env, project, site, command_log = _environment(tmp_path)

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "pull app-blue bot" in commands
    assert "run -T --rm --no-deps app-blue alembic upgrade head" in commands
    assert "up -d --no-deps --force-recreate app-blue" in commands
    assert "up -d --no-deps --force-recreate bot" in commands
    assert "stop app" in commands
    assert "rm -f app" in commands
    assert " pull db" not in commands
    assert " up -d db" not in commands
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "blue"
    assert (project / ".previous-backend-image").read_text(encoding="utf-8").strip() == OLD_IMAGE
    assert f"BACKEND_IMAGE={NEW_IMAGE}" in (project / ".env").read_text(encoding="utf-8")
    assert "proxy_pass http://127.0.0.1:18001;" in (
        tmp_path / "nginx/snippets/mvn-api-upstream.conf"
    ).read_text(encoding="utf-8")
    assert "listen 127.0.0.1:18080;" in Path(env["API_NGINX_INTERNAL_FILE"]).read_text(
        encoding="utf-8"
    )
    assert "include " in site.read_text(encoding="utf-8")


def test_bootstrap_only_installs_stable_proxy_without_container_changes(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["API_BLUE_GREEN_BOOTSTRAP_ONLY"] = "true"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert " pull " not in commands
    assert " up " not in commands
    assert " stop " not in commands
    assert not (project / ".active-api-slot").exists()
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(encoding="utf-8")
    assert "listen 127.0.0.1:18080;" in Path(env["API_NGINX_INTERNAL_FILE"]).read_text(
        encoding="utf-8"
    )


def test_next_deploy_uses_green_and_stops_blue(tmp_path):
    env, project, site, command_log = _environment(tmp_path)
    upstream = Path(env["API_NGINX_UPSTREAM_FILE"])
    upstream.parent.mkdir(parents=True, exist_ok=True)
    upstream.write_text("proxy_pass http://127.0.0.1:18001;\n", encoding="utf-8")
    site.write_text(
        f"server {{\n    location / {{\n        include {upstream};\n    }}\n}}\n",
        encoding="utf-8",
    )
    (project / ".active-api-slot").write_text("blue\n", encoding="utf-8")

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "pull app-green bot" in commands
    assert "up -d --no-deps --force-recreate app-green" in commands
    assert "stop app-blue" in commands
    assert "rm -f app-blue" in commands
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "green"
    assert "proxy_pass http://127.0.0.1:18002;" in upstream.read_text(encoding="utf-8")


def test_container_proxy_switches_by_service_name_without_host_nginx(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    proxy_dir = project / "api-proxy"
    proxy_dir.mkdir()
    (proxy_dir / "nginx.conf").write_text("events {}\nhttp {}\n", encoding="utf-8")
    upstream = proxy_dir / "upstream.conf"
    upstream.write_text("proxy_pass http://app:8000;\n", encoding="utf-8")
    env.update(
        {
            "API_PROXY_MODE": "container_nginx",
            "API_PROXY_CONFIG_FILE": str(proxy_dir / "nginx.conf"),
            "API_NGINX_UPSTREAM_FILE": str(upstream),
        }
    )

    result = _run(env)

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "up -d --no-deps api-proxy" in commands
    assert "exec -T api-proxy nginx -t" in commands
    assert "exec -T api-proxy nginx -s reload" in commands
    assert "proxy_pass http://app-blue:8000;" in upstream.read_text(encoding="utf-8")
    assert (project / ".active-api-slot").read_text(encoding="utf-8").strip() == "blue"


def test_failed_candidate_keeps_legacy_active(tmp_path):
    env, project, _, command_log = _environment(tmp_path)
    env["FAIL_CANDIDATE_READY"] = "true"

    result = _run(env)

    assert result.returncode != 0
    assert not (project / ".active-api-slot").exists()
    assert f"BACKEND_IMAGE={OLD_IMAGE}" in (project / ".env").read_text(encoding="utf-8")
    assert "proxy_pass http://127.0.0.1:8000;" in Path(
        env["API_NGINX_UPSTREAM_FILE"]
    ).read_text(encoding="utf-8")
    commands = command_log.read_text(encoding="utf-8")
    assert "stop app-blue" in commands
    assert not any(line.endswith(" stop app") for line in commands.splitlines())
