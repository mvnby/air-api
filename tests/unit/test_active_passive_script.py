import os
import subprocess
import textwrap
from pathlib import Path


SCRIPT = Path("scripts/ha/check_active_passive.sh")


def _write_fake_curl(tmp_path: Path, body: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_curl = bin_dir / "curl"
    fake_curl.write_text(body, encoding="utf-8")
    fake_curl.chmod(0o755)
    return bin_dir


def _run_check(tmp_path: Path, fake_curl_body: str) -> subprocess.CompletedProcess[str]:
    bin_dir = _write_fake_curl(tmp_path, fake_curl_body)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CHECK_PUBLIC_READY": "false",
            "READY_RETRIES": "2",
            "READY_RETRY_SLEEP": "0",
        }
    )
    return subprocess.run(
        ["bash", str(SCRIPT)],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_active_passive_retries_transient_invalid_standby_response(tmp_path):
    state_file = tmp_path / "standby-count"
    fake_curl = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        output=""
        args=("$@")
        for ((i=0; i<$#; i++)); do
          if [[ "${{args[$i]}}" == "-o" ]]; then
            output="${{args[$((i + 1))]}}"
          fi
        done
        joined=" $* "
        if [[ "${{joined}}" == *"193.47.42.213"* ]]; then
          count=0
          if [[ -f "{state_file}" ]]; then
            count="$(cat "{state_file}")"
          fi
          count=$((count + 1))
          printf '%s' "${{count}}" > "{state_file}"
          if (( count == 1 )); then
            printf '<html>restarting</html>' > "${{output}}"
            printf '503'
            exit 0
          fi
          printf '{{"app_role":"standby","api":"not_ready","traffic":"disabled"}}' > "${{output}}"
          printf '503'
          exit 0
        fi
        printf '{{"status":"ok","app_role":"primary","api":"ready","traffic":"enabled","database":"online","database_writable":true}}' > "${{output}}"
        printf '200'
        """
    )

    result = _run_check(tmp_path, fake_curl)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "standby direct ready retrying" in result.stderr
    assert state_file.read_text(encoding="utf-8") == "2"


def test_active_passive_fails_immediately_when_standby_returns_http_200(tmp_path):
    state_file = tmp_path / "standby-count"
    fake_curl = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        output=""
        args=("$@")
        for ((i=0; i<$#; i++)); do
          if [[ "${{args[$i]}}" == "-o" ]]; then
            output="${{args[$((i + 1))]}}"
          fi
        done
        joined=" $* "
        if [[ "${{joined}}" == *"193.47.42.213"* ]]; then
          count=0
          if [[ -f "{state_file}" ]]; then
            count="$(cat "{state_file}")"
          fi
          count=$((count + 1))
          printf '%s' "${{count}}" > "{state_file}"
          printf '{{"status":"ok","app_role":"standby","api":"ready","traffic":"enabled","database":"online","database_writable":true}}' > "${{output}}"
          printf '200'
          exit 0
        fi
        printf '{{"status":"ok","app_role":"primary","api":"ready","traffic":"enabled","database":"online","database_writable":true}}' > "${{output}}"
        printf '200'
        """
    )

    result = _run_check(tmp_path, fake_curl)

    assert result.returncode == 1
    assert "split-brain risk" in result.stderr
    assert state_file.read_text(encoding="utf-8") == "1"
