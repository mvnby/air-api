#!/usr/bin/env python3
"""Create and verify the exact root-owned Patroni remote helper bundle."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
MAX_FILE_SIZE = 2 * 1024 * 1024


def _read_regular(path: Path, *, owner: int, group: int | None = None) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != owner
        or (group is not None and before.st_gid != group)
        or before.st_nlink != 1
        or before.st_mode & 0o022
        or before.st_size > MAX_FILE_SIZE
    ):
        raise RuntimeError(f"unsafe bundle file metadata: {path.name}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"bundle file changed while opening: {path.name}")
        data = os.read(descriptor, MAX_FILE_SIZE + 1)
        if len(data) > MAX_FILE_SIZE or os.read(descriptor, 1):
            raise RuntimeError(f"bundle file is too large: {path.name}")
        after = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if tuple(getattr(after, key) for key in fields) != tuple(
            getattr(opened, key) for key in fields
        ):
            raise RuntimeError(f"bundle file changed while reading: {path.name}")
        return data
    finally:
        os.close(descriptor)


def create_manifest(paths: list[Path]) -> str:
    manifest: dict[str, str] = {}
    for path in paths:
        name = path.name
        if not NAME_RE.fullmatch(name) or name in manifest:
            raise RuntimeError(f"unsafe or duplicate bundle name: {name}")
        manifest[name] = hashlib.sha256(
            _read_regular(path, owner=os.geteuid())
        ).hexdigest()
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
    return base64.b64encode(raw).decode("ascii")


def verify_bundle(directory: Path, encoded_manifest: str) -> None:
    metadata = directory.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_gid != os.getegid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("remote bundle directory metadata is unsafe")
    try:
        manifest = json.loads(base64.b64decode(encoded_manifest, validate=True))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("remote bundle manifest is invalid") from exc
    if (
        not isinstance(manifest, dict)
        or not manifest
        or any(
            not isinstance(name, str)
            or not NAME_RE.fullmatch(name)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for name, digest in manifest.items()
        )
        or set(os.listdir(directory)) != set(manifest)
    ):
        raise RuntimeError("remote bundle contents differ from the exact manifest")
    for name, digest in manifest.items():
        actual = hashlib.sha256(
            _read_regular(
                directory / name, owner=os.geteuid(), group=os.getegid()
            )
        ).hexdigest()
        if actual != digest:
            raise RuntimeError(f"remote bundle source digest mismatch: {name}")


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in {"manifest", "verify"}:
        raise RuntimeError("usage: verify_patroni_remote_bundle.py manifest FILE... | verify DIR MANIFEST")
    if sys.argv[1] == "manifest":
        print(create_manifest([Path(value) for value in sys.argv[2:]]))
        return 0
    if len(sys.argv) != 4:
        raise RuntimeError("verify requires exactly a directory and manifest")
    verify_bundle(Path(sys.argv[2]), sys.argv[3])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"patroni_remote_bundle status=failed error={exc}", file=sys.stderr)
        raise SystemExit(1)
