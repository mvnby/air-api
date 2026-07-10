import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/post_deploy_smoke_check.sh"


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_smoke_check_resolves_active_green_service(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    compose = project / "docker-compose.prod.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    (project / ".active-api-slot").write_text("green\n", encoding="utf-8")

    command_log = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
url="${*: -1}"
case "$url" in
  */api/ready) printf '{"status":"ok","api":"ready","traffic":"enabled","database":"online"}\n' ;;
  */api/health|*/health) printf '{"status":"ok","database":"online"}\n' ;;
  *products*) printf '{"items":[]}\n' ;;
  *filters/config*) printf '{"price":{},"area":{},"brands":[],"expert_tags":[]}\n' ;;
  *) exit 22 ;;
esac
""",
    )
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$COMMAND_LOG"
if [[ "$*" == *"ps --status running --services"* ]]; then
  printf 'app-green\nbot\n'
elif [[ "$*" == *"exec -T bot python3 -"* ]]; then
  printf 'enabled=true\nreason=test\n'
fi
exit 0
""",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "COMMAND_LOG": str(command_log),
            "BASE_URL": "http://test",
            "READY_URL": "http://test/api/ready",
            "COMPOSE_FILE": str(compose),
            "MAX_RETRIES": "1",
            "RETRY_DELAY": "0",
            "SMOKE_SUMMARY_FILE": str(tmp_path / "summary.txt"),
        }
    )

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = command_log.read_text(encoding="utf-8")
    assert "--profile bluegreen ps --status running --services" in calls
    assert "exec -T bot python3 -" in calls
    assert "Compose services running: app-green bot" in result.stdout
