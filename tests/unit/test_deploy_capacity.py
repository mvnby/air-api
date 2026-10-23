import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts/ha/require_deploy_capacity.sh"


def _run(tmp_path: Path, meminfo: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    meminfo_file = tmp_path / "meminfo"
    meminfo_file.write_text(meminfo, encoding="utf-8")
    return subprocess.run(
        ["bash", "-c", 'source "$1"; require_deploy_capacity', "capacity-test", str(HELPER)],
        env={
            **os.environ,
            "API_DEPLOY_MEMINFO_FILE": str(meminfo_file),
            **overrides,
        },
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    "swap",
    [
        "SwapTotal: 0 kB\nSwapFree: 0 kB\n",
        "SwapTotal: 524288 kB\nSwapFree: 262144 kB\n",
    ],
)
def test_capacity_accepts_exact_primary_memory_boundary_with_safe_swap(tmp_path, swap):
    result = _run(tmp_path, "MemAvailable: 1572864 kB\n" + swap)

    assert result.returncode == 0, result.stderr


def test_capacity_reserve_profile_accepts_one_gib_boundary(tmp_path):
    result = _run(
        tmp_path,
        "MemAvailable: 1048576 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
        API_DEPLOY_CAPACITY_PROFILE="reserve",
    )

    assert result.returncode == 0, result.stderr


def test_capacity_rejects_unknown_profile_before_meminfo_read(tmp_path):
    result = _run(
        tmp_path,
        "MemAvailable: 2097152 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
        API_DEPLOY_CAPACITY_PROFILE="unknown",
    )

    assert result.returncode != 0
    assert "must be primary or reserve" in result.stderr


def test_capacity_rejects_exhausted_memory_and_swap(tmp_path):
    result = _run(
        tmp_path,
        "MemAvailable: 201868 kB\nSwapTotal: 2621432 kB\nSwapFree: 3804 kB\n",
    )

    assert result.returncode != 0
    assert "insufficient memory headroom" in result.stderr


def test_capacity_rejects_low_swap_even_with_free_memory(tmp_path):
    result = _run(
        tmp_path,
        "MemAvailable: 2097152 kB\nSwapTotal: 524288 kB\nSwapFree: 131072 kB\n",
    )

    assert result.returncode != 0
    assert "insufficient free swap reserve" in result.stderr


@pytest.mark.parametrize(
    "meminfo",
    [
        "MemAvailable: 2097152 kB\nMemAvailable: 2097152 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
        "MemAvailable: 2097152 kB\nSwapTotal: 0 kB\n",
        "MemAvailable: unknown kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
        "MemAvailable: 2097152 MB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
        "MemAvailable: 2097152 kB extra\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
    ],
)
def test_capacity_rejects_ambiguous_or_invalid_meminfo(tmp_path, meminfo):
    result = _run(tmp_path, meminfo)

    assert result.returncode != 0


@pytest.mark.parametrize("case", [
    "disabled", "missing-lock", "unsupported-operation", "owned-journal",
    "invalid-meminfo", "invalid-swap", "swap-only",
])
def test_idle_relief_is_not_invoked_outside_eligible_memory_failure(tmp_path, case):
    guard = tmp_path / "guard.py"
    called = tmp_path / "called"
    guard.write_text(f"from pathlib import Path\nPath({str(called)!r}).touch()\n")
    overrides = {
        "API_IDLE_WORKER_CAPACITY_RELIEF_ALLOWED": "true",
        "API_IDLE_WORKER_CAPACITY_GUARD": str(guard),
        "API_DEPLOY_LOCK_FD": "9",
        "PATRONI_CANDIDATE_OPERATION": "deploy",
        "API_PROJECT_DIR": str(tmp_path),
    }
    memory = "MemAvailable: 1550000 kB\nSwapTotal: 524288 kB\nSwapFree: 524288 kB\n"
    if case == "disabled": overrides["API_IDLE_WORKER_CAPACITY_RELIEF_ALLOWED"] = "false"
    if case == "missing-lock": overrides["API_DEPLOY_LOCK_FD"] = ""
    if case == "unsupported-operation": overrides["PATRONI_CANDIDATE_OPERATION"] = "scrub"
    if case == "owned-journal": (tmp_path / ".ha-idle-worker-capacity.json").write_text("{}")
    if case == "invalid-meminfo": memory = memory.replace("1550000 kB", "invalid kB")
    if case == "invalid-swap": memory = memory.replace("SwapFree: 524288", "SwapFree: 524289")
    if case == "swap-only": memory = memory.replace("1550000", "2097152").replace("SwapFree: 524288", "SwapFree: 1000")
    result = _run(tmp_path, memory, **overrides)
    assert result.returncode != 0
    assert not called.exists()
