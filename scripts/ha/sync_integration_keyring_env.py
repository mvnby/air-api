#!/usr/bin/env python3
"""Replace only the integration keyring in a locked server env file via stdin."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path


SETTING = "INTEGRATION_CREDENTIAL_KEYRING_JSON"
MAX_ENV_BYTES = 1024 * 1024


def render_env(current: str, secret_json: str) -> str:
    if len(secret_json.encode()) > 16384 or "\0" in secret_json:
        raise ValueError("invalid keyring input")
    payload = json.loads(secret_json)
    if not isinstance(payload, dict) or set(payload) != {
        "active_key_id", "write_mode", "keys", "legacy_secret_keys",
    }:
        raise ValueError("invalid keyring fields")
    if payload["write_mode"] not in {"legacy", "active"}:
        raise ValueError("invalid write mode")
    if not isinstance(payload["keys"], dict) or not isinstance(payload["legacy_secret_keys"], list):
        raise ValueError("invalid keyring collections")
    if payload["active_key_id"] not in payload["keys"]:
        raise ValueError("active key missing")
    # An unquoted JSON object has identical backslash semantics in Compose and
    # python-dotenv. Encode interpolation/comment markers as JSON unicode
    # escapes so neither dotenv reader expands or truncates key material.
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    serialized = serialized.replace("$", "\\u0024").replace("#", "\\u0023")
    replacement = f"{SETTING}={serialized}"
    output = []
    found = False
    for line in current.splitlines():
        if re.match(rf"^\s*(?:export\s+)?{SETTING}\s*=", line):
            if found:
                raise ValueError("duplicate keyring setting")
            output.append(replacement)
            found = True
        else:
            output.append(line)
    if not found:
        output.append(replacement)
    return "\n".join(output).rstrip("\n") + "\n"


def sync_env(path: Path, secret_json: str, expected_sha256: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("expected env digest required")
    # The caller must hold the same descriptor as the production release.
    if os.environ.get("API_DEPLOY_LOCK_FD") != "9":
        raise ValueError("deployment lock required")
    from safe_deploy_lock import _verify
    _verify(str(path.parent / ".deploy.lock"), 9)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_uid != os.geteuid() or before.st_mode & 0o022
            or before.st_size > MAX_ENV_BYTES):
        raise ValueError("unsafe env file")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read(MAX_ENV_BYTES + 1)
    if ((before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise ValueError("env changed since review")
    rendered = render_env(raw.decode("utf-8"), secret_json)
    fd, filename = tempfile.mkstemp(prefix=".integration-keyring-", dir=path.parent)
    temporary = Path(filename)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, before.st_uid, before.st_gid)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        current = path.lstat()
        if (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size) != (
            before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size,
        ):
            raise ValueError("env changed during update")
        os.replace(temporary, path)
        parent_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--expected-env-sha256", required=True)
    args = parser.parse_args()
    try:
        sync_env(args.env_file, sys.stdin.read(16385), args.expected_env_sha256)
    except Exception:
        print("integration_keyring_env status=failed", file=sys.stderr)
        return 1
    print("integration_keyring_env status=updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
