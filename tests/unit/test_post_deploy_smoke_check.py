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
output_file=""
write_format=""
url=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) output_file="$2"; shift 2 ;;
    -w) write_format="$2"; shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
case "$url" in
  */api/ready) payload='{"status":"ok","api":"ready","traffic":"enabled","database":"online"}'; status=200 ;;
  */api/health|*/health) payload='{"status":"ok","database":"online"}'; status=200 ;;
  *products*) payload='{"items":[]}'; status=200 ;;
  *filters/config*) payload='{"price":{},"area":{},"brands":[],"expert_tags":[]}'; status=200 ;;
  *) exit 22 ;;
esac
if [[ -n "$output_file" ]]; then
  printf '%s\n' "$payload" > "$output_file"
else
  printf '%s\n' "$payload"
fi
[[ -z "$write_format" ]] || printf '%s' "$status"
""",
    )
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$COMMAND_LOG"
if [[ "$*" == *"ps --status running --services"* ]]; then
      printf 'app-green\n'
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
    assert "exec -T bot python3 -" not in calls
    assert "Compose services running: app-green" in result.stdout
