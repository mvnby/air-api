#!/usr/bin/env python3
"""Run rembg in an isolated process for one image."""

from __future__ import annotations

import argparse
import os
import sys


def _positive_int_from_env(name: str) -> int | None:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        return None
    return value if value > 0 else None


def _apply_resource_limits() -> None:
    try:
        import resource
    except ImportError:
        return

    memory_mb = _positive_int_from_env("BACKGROUND_REMOVAL_PROCESS_MAX_MEMORY_MB")
    if memory_mb:
        memory_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

    cpu_seconds = _positive_int_from_env("BACKGROUND_REMOVAL_PROCESS_MAX_CPU_SECONDS")
    if cpu_seconds:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _apply_resource_limits()

    try:
        from rembg import new_session, remove  # type: ignore
    except ImportError as exc:
        print(f"rembg provider is not installed: {exc}", file=sys.stderr)
        return 2

    try:
        with open(args.input, "rb") as input_file:
            source_content = input_file.read()
        session = new_session(args.model)
        output = remove(source_content, session=session)
        with open(args.output, "wb") as output_file:
            output_file.write(output)
    except Exception as exc:
        print(f"rembg failed for {args.model}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
