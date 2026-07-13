#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Sequence


DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_PROBE_TIMEOUT_SECONDS = 5.0
DEFAULT_STABLE_SAMPLES = 3
DEFAULT_SAMPLE_INTERVAL_SECONDS = 2.0
MAX_TERM_GRACE_SECONDS = 0.2
MAX_REAP_GRACE_SECONDS = 0.05
POSTMASTER_QUERY = "SELECT pg_postmaster_start_time()::text;"

COMPOSE_SERVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
POSTGRES_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class WaitConfig:
    service: str
    database: str
    user: str
    timeout_seconds: float
    probe_timeout_seconds: float
    stable_samples: int
    sample_interval_seconds: float


@dataclass(frozen=True)
class ProbeResult:
    returncode: int
    stdout: str
    timed_out: bool


def _positive_float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a positive number") from exc
    if not math.isfinite(value) or not value > 0:
        raise ConfigurationError(f"{name} must be a positive number")
    return value


def _stable_samples_env() -> int:
    raw_value = os.environ.get("POSTGRES_WAIT_STABLE_SAMPLES")
    if raw_value is None:
        return DEFAULT_STABLE_SAMPLES
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(
            "POSTGRES_WAIT_STABLE_SAMPLES must be an integer of at least 2"
        ) from exc
    if value < 2 or str(value) != raw_value:
        raise ConfigurationError(
            "POSTGRES_WAIT_STABLE_SAMPLES must be an integer of at least 2"
        )
    return value


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wait for a stable PostgreSQL postmaster in a Compose service."
    )
    parser.add_argument("service")
    parser.add_argument("database")
    parser.add_argument("user", nargs="?", default="postgres")
    return parser.parse_args(argv)


def _load_config(argv: Sequence[str] | None) -> WaitConfig:
    args = _parse_args(argv)
    if not COMPOSE_SERVICE_RE.fullmatch(args.service):
        raise ConfigurationError(f"invalid Compose service name: {args.service}")
    if not POSTGRES_IDENTIFIER_RE.fullmatch(args.database):
        raise ConfigurationError(f"invalid database name: {args.database}")
    if not POSTGRES_IDENTIFIER_RE.fullmatch(args.user):
        raise ConfigurationError(f"invalid database user: {args.user}")

    return WaitConfig(
        service=args.service,
        database=args.database,
        user=args.user,
        timeout_seconds=_positive_float_env(
            "POSTGRES_WAIT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS
        ),
        probe_timeout_seconds=_positive_float_env(
            "POSTGRES_WAIT_PROBE_TIMEOUT_SECONDS", DEFAULT_PROBE_TIMEOUT_SECONDS
        ),
        stable_samples=_stable_samples_env(),
        sample_interval_seconds=_positive_float_env(
            "POSTGRES_WAIT_SAMPLE_INTERVAL_SECONDS",
            DEFAULT_SAMPLE_INTERVAL_SECONDS,
        ),
    )


def _signal_process_group(process_group_id: int, sig: signal.Signals) -> None:
    try:
        os.killpg(process_group_id, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        # A finished group ID may already have been reused by another user.
        # Refuse to signal a process group that is no longer ours.
        pass


def _drain_after_kill(
    process: subprocess.Popen[str],
    *,
    deadline: float,
) -> None:
    remaining = max(0.001, deadline - time.monotonic())
    try:
        process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        if process.stdout is not None:
            process.stdout.close()
        process.kill()
        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass


def run_with_process_group_timeout(
    command: Sequence[str],
    *,
    timeout_seconds: float,
) -> ProbeResult:
    started_at = time.monotonic()
    deadline = started_at + timeout_seconds
    term_grace = min(MAX_TERM_GRACE_SECONDS, timeout_seconds / 4)
    reap_grace = min(MAX_REAP_GRACE_SECONDS, timeout_seconds / 4)
    kill_deadline = deadline - reap_grace
    term_deadline = kill_deadline - term_grace

    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    try:
        soft_timeout = max(0.001, term_deadline - time.monotonic())
        stdout, _ = process.communicate(timeout=soft_timeout)
        if time.monotonic() > deadline:
            return ProbeResult(returncode=124, stdout="", timed_out=True)
        return ProbeResult(
            returncode=process.returncode,
            stdout=stdout,
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        _signal_process_group(process.pid, signal.SIGTERM)
        remaining = kill_deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

        # The group kill is unconditional after the TERM grace. The original
        # leader may already be gone while a descendant still owns stdout.
        _signal_process_group(process.pid, signal.SIGKILL)
        cleanup_deadline = min(
            deadline,
            time.monotonic() + MAX_REAP_GRACE_SECONDS,
        )
        _drain_after_kill(process, deadline=cleanup_deadline)
        return ProbeResult(returncode=124, stdout="", timed_out=True)
    except BaseException:
        _signal_process_group(process.pid, signal.SIGKILL)
        cleanup_deadline = min(
            deadline,
            time.monotonic() + MAX_REAP_GRACE_SECONDS,
        )
        _drain_after_kill(process, deadline=cleanup_deadline)
        raise


def _timeout_error(config: WaitConfig) -> str:
    timeout = f"{config.timeout_seconds:g}"
    return (
        f"PostgreSQL service {config.service} did not produce "
        f"{config.stable_samples} stable SQL samples within {timeout}s"
    )


def _probe_command(docker: str, config: WaitConfig) -> list[str]:
    return [
        docker,
        "compose",
        "exec",
        "-T",
        config.service,
        "psql",
        "-X",
        "-w",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        config.user,
        "-d",
        config.database,
        "-tAc",
        POSTMASTER_QUERY,
    ]


def wait_for_stable_postgres(config: WaitConfig, *, docker: str) -> int:
    started_at = time.monotonic()
    deadline = started_at + config.timeout_seconds
    attempt = 0
    stable_samples = 0
    last_start_time = ""
    timeout_label = f"{config.timeout_seconds:g}"

    print(
        f"Waiting up to {timeout_label}s for PostgreSQL service {config.service} "
        f"({config.database}) to remain on one postmaster for "
        f"{config.stable_samples} SQL samples..."
    )

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"ERROR: {_timeout_error(config)}", file=sys.stderr)
            return 1

        attempt += 1
        probe_budget = min(config.probe_timeout_seconds, remaining)
        result = run_with_process_group_timeout(
            _probe_command(docker, config),
            timeout_seconds=probe_budget,
        )
        sample = result.stdout.rstrip("\r\n")
        valid_sample = (
            result.returncode == 0
            and not result.timed_out
            and bool(sample)
            and "\n" not in sample
            and "\r" not in sample
        )

        if valid_sample:
            if sample == last_start_time:
                stable_samples += 1
            else:
                if last_start_time:
                    print(
                        f"PostgreSQL service {config.service} restarted; "
                        "resetting stability samples."
                    )
                last_start_time = sample
                stable_samples = 1

            print(
                f"PostgreSQL service {config.service} SQL sample "
                f"{stable_samples}/{config.stable_samples} uses postmaster {sample}."
            )
            if stable_samples >= config.stable_samples:
                elapsed = time.monotonic() - started_at
                if elapsed > config.timeout_seconds:
                    print(f"ERROR: {_timeout_error(config)}", file=sys.stderr)
                    return 1
                print(
                    f"PostgreSQL service {config.service} is stable after "
                    f"{elapsed:.2f}s and {attempt} attempts."
                )
                return 0
        else:
            if stable_samples:
                print(
                    f"PostgreSQL service {config.service} SQL probe failed; "
                    "resetting stability samples."
                )
            else:
                print(
                    f"PostgreSQL service {config.service} SQL probe is not ready "
                    f"(attempt {attempt})."
                )
            stable_samples = 0
            last_start_time = ""

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"ERROR: {_timeout_error(config)}", file=sys.stderr)
            return 1
        time.sleep(min(config.sample_interval_seconds, remaining))


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = _load_config(argv)
    except ConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    docker = shutil.which("docker")
    if docker is None:
        print("ERROR: docker is required", file=sys.stderr)
        return 1
    return wait_for_stable_postgres(config, docker=docker)


if __name__ == "__main__":
    raise SystemExit(main())
