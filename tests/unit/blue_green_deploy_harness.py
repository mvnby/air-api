import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/deploy_backend_blue_green.sh"
SAFETY_SCRIPT = REPO_ROOT / "scripts/deploy_backend_blue_green_safety.sh"
OLD_IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "1" * 64
NEW_IMAGE = "ghcr.io/mvnby/air-api/backend@sha256:" + "2" * 64


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "docker-compose.prod.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )
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
        fake_bin / "mv",
        """#!/usr/bin/env bash
source_path=""
destination_path=""
for argument in "$@"; do
  source_path="$destination_path"
  destination_path="$argument"
done
if [[ "$destination_path" == "$API_PROJECT_DIR/.env" ]]; then
  if [[ "${FAIL_PREVIOUS_ENV_WRITE:-false}" == "true" ]] \
    && grep -Fq "BACKEND_IMAGE=$TEST_OLD_IMAGE" "$source_path"; then
    exit 1
  fi
  if [[ "${FAIL_REQUESTED_ENV_WRITE_AFTER_OLD_STOP:-false}" == "true" ]] \
    && grep -Fq "BACKEND_IMAGE=$TEST_NEW_IMAGE" "$source_path"; then
    old_stops="$(grep -Ec ' stop -t [0-9]+ app$' "$COMMAND_LOG" || true)"
    if (( old_stops >= 2 )); then
      exit 1
    fi
  fi
fi
exec /bin/mv "$@"
""",
    )
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -u
printf 'docker %s\n' "$*" >> "$COMMAND_LOG"
if [[ "${1:-}" == "inspect" ]]; then
  case "${*: -1}" in
    cid-app) runtime_image="${FAKE_RUNTIME_APP_IMAGE:-}" ;;
    cid-app-blue) runtime_image="${FAKE_RUNTIME_APP_BLUE_IMAGE:-}" ;;
    cid-app-green) runtime_image="${FAKE_RUNTIME_APP_GREEN_IMAGE:-}" ;;
    cid-bot) runtime_image="${FAKE_RUNTIME_BOT_IMAGE:-}" ;;
    *) exit 1 ;;
  esac
  [[ -n "$runtime_image" ]] || exit 1
  printf '%s\n' "$runtime_image"
  exit 0
fi
if [[ "$*" == *" ps -q "* ]]; then
  case "${*: -1}" in
    app) runtime_image="${FAKE_RUNTIME_APP_IMAGE:-}" ;;
    app-blue) runtime_image="${FAKE_RUNTIME_APP_BLUE_IMAGE:-}" ;;
    app-green) runtime_image="${FAKE_RUNTIME_APP_GREEN_IMAGE:-}" ;;
    bot) runtime_image="${FAKE_RUNTIME_BOT_IMAGE:-}" ;;
    *) runtime_image="" ;;
  esac
  [[ -n "$runtime_image" ]] && printf 'cid-%s\n' "${*: -1}"
  exit 0
fi
if [[ "$*" == *" up -d --no-deps --force-recreate bot" ]]; then
  printf 'bot_image %s\n' "${BACKEND_IMAGE:-}" >> "$COMMAND_LOG"
fi
previous=""
for argument in "$@"; do
  if [[ "$previous" == "-f" && "$argument" == *"rollback-api-buffer.compose.yml" && -f "$argument" ]]; then
    sed 's/^/override /' "$argument" >> "$COMMAND_LOG"
  fi
  previous="$argument"
done
if [[ "$*" == *"nginx -s reload"* && -f "${UPSTREAM_FILE:-}" ]]; then
  sed 's/^/upstream /' "$UPSTREAM_FILE" >> "$COMMAND_LOG"
fi
if [[ "${FAIL_CANDIDATE_STOP:-false}" == "true" && "$*" == *" stop -t 5 app-blue" ]]; then
  exit 1
fi
if [[ "${FAIL_INITIAL_ACTIVE_STOP:-false}" == "true" && "$*" == *" stop -t 5 app" ]]; then
  exit 1
fi
if [[ "${FAIL_BUFFER_REMOVE:-false}" == "true" && "$*" == *" rm -s -f app-green" ]]; then
  exit 1
fi
if [[ "${FAIL_BUFFER_START:-false}" == "true" && "$*" == *"rollback-api-buffer.compose.yml"* && "$*" == *" up -d --no-deps --force-recreate app-green" ]]; then
  exit 1
fi
if [[ "${FAIL_OLD_STOP:-false}" == "true" && "$*" == *" stop -t 5 app" ]]; then
  old_stops="$(grep -Ec ' stop -t [0-9]+ app$' "$COMMAND_LOG" || true)"
  if (( old_stops >= 2 )); then
    exit 1
  fi
fi
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
if [[ "${FAIL_ROLLBACK_OLD_READY:-false}" == "true" && "$url" == *":8000/api/ready"* ]]; then
  exit 22
fi
if [[ "${FAIL_PUBLIC_READY:-false}" == "true" && "$url" == "https://public.test/api/ready" ]]; then
  exit 22
fi
case "$url" in
  */api/ready)
    scheduler_status="running"
    if [[ "${FAIL_SCHEDULER_RUNNING:-false}" == "true" ]]; then
      scheduler_status="retrying"
    elif [[ "${FAIL_SCHEDULER_AFTER_ROUTE_FAILURE:-false}" == "true" ]] \
      && [[ "$url" == *":18001/api/ready"* ]] \
      && grep -Fq 'rollback_old_route_failed' "$COMMAND_LOG"; then
      scheduler_status="retrying"
    elif [[ "${FAIL_SCHEDULER_BEFORE_FALLBACK:-false}" == "true" ]]; then
      candidate_recreates="$(grep -c 'up -d --no-deps --force-recreate app-blue' "$COMMAND_LOG" || true)"
      if (( candidate_recreates < 2 )); then
        scheduler_status="retrying"
      fi
    fi
    printf '{"status":"ok","api":"ready","database":"online","database_writable":true,"scheduler_runtime":{"expected":true,"status":"%s","reason":"scheduler_loop_running","changed_at":"2026-07-13T08:00:00+00:00"}}\n' "$scheduler_status"
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
        """#!/usr/bin/env bash
printf 'systemctl %s\n' "$*" >> "$COMMAND_LOG"
if [[ "$*" == *"reload nginx"* && -f "${UPSTREAM_FILE:-}" ]]; then
  sed 's/^/upstream /' "$UPSTREAM_FILE" >> "$COMMAND_LOG"
  if [[ "${FAIL_ROLLBACK_OLD_ROUTE:-false}" == "true" ]] \
    && grep -Fq 'proxy_pass http://127.0.0.1:8000;' "$UPSTREAM_FILE" \
    && grep -Fq 'upstream proxy_pass http://127.0.0.1:18001;' "$COMMAND_LOG"; then
    printf 'rollback_old_route_failed\n' >> "$COMMAND_LOG"
    exit 1
  fi
fi
exit 0
""",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "UPSTREAM_FILE": str(upstream),
            "TEST_OLD_IMAGE": OLD_IMAGE,
            "TEST_NEW_IMAGE": NEW_IMAGE,
            "FAKE_RUNTIME_APP_IMAGE": OLD_IMAGE,
            "FAKE_RUNTIME_BOT_IMAGE": OLD_IMAGE,
            "API_PROJECT_DIR": str(project),
            "API_COMPOSE_FILE": "docker-compose.prod.yml",
            "API_NGINX_SITE_FILE": str(site),
            "API_NGINX_UPSTREAM_FILE": str(upstream),
            "API_NGINX_INTERNAL_FILE": str(nginx_dir / "conf.d/mvn-api-internal.conf"),
            "API_BLUE_GREEN_SUMMARY_FILE": str(tmp_path / "summary.txt"),
            "API_HEALTH_ATTEMPTS": "2",
            "API_SCHEDULER_READY_ATTEMPTS": "6",
            "API_SCHEDULER_STABILITY_SECONDS": "0",
            "API_SERVICE_STOP_TIMEOUT_SECONDS": "5",
            "API_HEALTH_DELAY_SECONDS": "0",
            "API_DRAIN_SECONDS": "0",
            "BACKEND_IMAGE": NEW_IMAGE,
            "GHCR_PAT": "test-token",
            "GITHUB_ACTOR": "test-user",
            "GOOGLE_OAUTH_TOKEN_REQUIRED": "false",
        }
    )
    return env, project, site, command_log


def run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def configure_active_slot(
    env: dict[str, str],
    project: Path,
    site: Path,
    active_slot: str,
    proxy_mode: str,
) -> Path:
    service = {"legacy": "app", "blue": "app-blue", "green": "app-green"}[
        active_slot
    ]
    port = {"legacy": 8000, "blue": 18001, "green": 18002}[active_slot]

    if proxy_mode == "container_nginx":
        proxy_dir = project / "api-proxy"
        proxy_dir.mkdir(exist_ok=True)
        (proxy_dir / "nginx.conf").write_text("events {}\nhttp {}\n", encoding="utf-8")
        upstream = proxy_dir / "upstream.conf"
        upstream.write_text(f"proxy_pass http://{service}:8000;\n", encoding="utf-8")
        env.update(
            {
                "API_PROXY_MODE": "container_nginx",
                "API_PROXY_CONFIG_FILE": str(proxy_dir / "nginx.conf"),
                "API_NGINX_UPSTREAM_FILE": str(upstream),
                "UPSTREAM_FILE": str(upstream),
            }
        )
    else:
        upstream = Path(env["API_NGINX_UPSTREAM_FILE"])
        upstream.parent.mkdir(parents=True, exist_ok=True)
        upstream.write_text(f"proxy_pass http://127.0.0.1:{port};\n", encoding="utf-8")
        site.write_text(
            f"server {{\n    location / {{\n        include {upstream};\n    }}\n}}\n",
            encoding="utf-8",
        )

    active_file = project / ".active-api-slot"
    env[f"FAKE_RUNTIME_{service.upper().replace('-', '_')}_IMAGE"] = OLD_IMAGE
    if active_slot == "legacy":
        active_file.unlink(missing_ok=True)
    else:
        active_file.write_text(f"{active_slot}\n", encoding="utf-8")
    return upstream
