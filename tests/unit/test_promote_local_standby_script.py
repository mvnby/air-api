import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ha/promote_local_standby.sh"


def run_script(*args, env=None):
    merged_env = os.environ.copy()
    merged_env.update(env or {})
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        check=False,
        capture_output=True,
        env=merged_env,
        text=True,
    )


def test_promote_refuses_without_old_primary_fencing(tmp_path):
    result = run_script(
        env={
            "CONFIRM_PROMOTE": "true",
            "PROJECT_DIR": str(tmp_path),
            "OLD_PRIMARY_SSH": "",
            "ALLOW_UNFENCED_PROMOTE": "false",
        }
    )

    assert result.returncode == 1
    assert "Refusing to promote without OLD_PRIMARY_SSH fencing" in result.stderr
    assert "ALLOW_UNFENCED_PROMOTE=true" in result.stderr


def test_promote_allow_unfenced_requires_explicit_opt_in(tmp_path):
    result = run_script(
        "--allow-unfenced",
        env={
            "CONFIRM_PROMOTE": "true",
            "PROJECT_DIR": str(tmp_path),
            "OLD_PRIMARY_SSH": "",
            "ALLOW_UNFENCED_PROMOTE": "false",
        },
    )

    assert result.returncode == 1
    assert "Compose file not found" in result.stderr
    assert "Refusing to promote without OLD_PRIMARY_SSH fencing" not in result.stderr


def test_promote_help_documents_unfenced_guard():
    result = run_script("--help")

    assert result.returncode == 0
    assert "ALLOW_UNFENCED_PROMOTE=false" in result.stdout
    assert "--allow-unfenced" in result.stdout
