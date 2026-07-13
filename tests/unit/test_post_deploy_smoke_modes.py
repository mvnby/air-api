import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = REPO_ROOT / "scripts/post_deploy_smoke_check.sh"


def _run_smoke(tmp_path: Path, *, mode: str, expectation: str):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
output_file=""
url=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    -o) output_file="$2"; shift 2 ;;
    -w) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
case "$url" in
  */api/ready)
    if [[ "$READY_MODE" == "fenced" ]]; then
      payload='{"status":"degraded","api":"not_ready","traffic":"disabled","database":"online"}'
      status=503
    else
      payload='{"status":"ok","api":"ready","traffic":"enabled","database":"online"}'
      status=200
    fi
    printf '%s' "$payload" > "$output_file"
    printf '%s' "$status"
    ;;
  */api/v1/products*) printf '{"items":[]}' ;;
  */api/v1/filters/config) printf '{"price":{},"area":{},"brands":[],"expert_tags":[]}' ;;
  */health|*/api/health) printf '{"status":"ok","database":"online"}' ;;
  *) exit 22 ;;
esac
""",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == "compose version" ]]; then exit 0; fi
if [[ "$*" == *"ps --status running --services"* ]]; then
  printf 'app\n'
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    compose = tmp_path / "compose.yml"
    compose.write_text("services:\n  app:\n    image: test\n", encoding="utf-8")
    summary = tmp_path / "summary.txt"
    result = subprocess.run(
        ["bash", str(SMOKE_SCRIPT)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "READY_MODE": mode,
            "BASE_URL": "http://127.0.0.1:18080",
            "READY_URL": "http://127.0.0.1:18080/api/ready",
            "READY_EXPECTATION": expectation,
            "COMPOSE_FILE": str(compose),
            "COMPOSE_SERVICE_CHECKS": "app",
            "BOT_EXPECT_ENABLED": "false",
            "SMOKE_SUMMARY_FILE": str(summary),
            "MAX_RETRIES": "1",
            "RETRY_DELAY": "0",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    return result, summary


def test_smoke_accepts_locally_healthy_but_fenced_standby(tmp_path):
    result, summary = _run_smoke(tmp_path, mode="fenced", expectation="fenced")

    assert result.returncode == 0, result.stderr
    text = summary.read_text(encoding="utf-8")
    assert "smoke_status=passed" in text
    assert "readiness_fenced" in text


def test_smoke_rejects_fenced_payload_when_active_readiness_is_required(tmp_path):
    result, _ = _run_smoke(tmp_path, mode="fenced", expectation="ready")

    assert result.returncode != 0
    assert "readiness payload is not ready" in result.stderr


def test_smoke_accepts_active_ready_payload(tmp_path):
    result, summary = _run_smoke(tmp_path, mode="ready", expectation="ready")

    assert result.returncode == 0, result.stderr
    assert "readiness_ready" in summary.read_text(encoding="utf-8")
