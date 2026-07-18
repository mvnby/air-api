#!/usr/bin/env python3
"""Atomically sync bot voice transcription settings into a server env file."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path


VOICE_ENV = {
    "BOT_VOICE_TRANSCRIPTION_ENABLED": "true",
    "BOT_VOICE_TRANSCRIPTION_API_URL": (
        "https://api.groq.com/openai/v1/audio/transcriptions"
    ),
    "BOT_VOICE_TRANSCRIPTION_MODEL": "whisper-large-v3-turbo",
    "BOT_VOICE_TRANSCRIPTION_TIMEOUT_SECONDS": "30",
}
MAX_ENV_BYTES = 1024 * 1024


def _validate_secret(secret: str) -> None:
    if not secret or "\n" in secret or "\r" in secret or "\0" in secret:
        raise ValueError("voice transcription API key is missing or malformed")


def render_env(current: str, secret: str) -> str:
    _validate_secret(secret)
    replacements = {**VOICE_ENV, "BOT_VOICE_TRANSCRIPTION_API_KEY": secret}
    output: list[str] = []
    seen: set[str] = set()
    for line in current.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in replacements:
            if key not in seen:
                output.append(f"{key}={replacements[key]}")
                seen.add(key)
            continue
        output.append(line)
    for key, value in replacements.items():
        if key not in seen:
            output.append(f"{key}={value}")
    return "\n".join(output).rstrip("\n") + "\n"


def sync_env(path: Path, secret: str) -> None:
    _validate_secret(secret)
    file_stat = path.lstat()
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise ValueError("env file must be a regular non-symlink file")
    if file_stat.st_size > MAX_ENV_BYTES:
        raise ValueError("env file is unexpectedly large")

    current = path.read_text(encoding="utf-8")
    rendered = render_env(current, secret)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, stat.S_IMODE(file_stat.st_mode))
        os.fchown(fd, file_stat.st_uid, file_stat.st_gid)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        sync_env(args.env_file, sys.stdin.read())
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"voice env sync failed: {exc}", file=sys.stderr)
        return 1
    print("voice transcription settings synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
