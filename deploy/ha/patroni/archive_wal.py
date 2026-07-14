#!/usr/bin/env python3
"""Durably archive one immutable PostgreSQL WAL file without overwriting."""

from __future__ import annotations

import hashlib
import fcntl
import os
import re
import stat
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path


ARCHIVE_ROOT = Path("/postgres-wal-archive")
ARCHIVABLE_WAL_RE = re.compile(
    r"^(?:[0-9A-F]{24}(?:\.partial)?|[0-9A-F]{24}\.[0-9A-F]{8}\.backup|[0-9A-F]{8}\.history)$"
)
WAL_SEGMENT_ARCHIVE_RE = re.compile(r"^[0-9A-F]{24}(?:\.partial)?$")
WAL_SEGMENT_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
LOCK_NAME = ".mvn-pitr-archive.lock"
TEMP_RE = re.compile(
    r"^\.((?:[0-9A-F]{24}(?:\.partial)?|[0-9A-F]{24}\.[0-9A-F]{8}\.backup|[0-9A-F]{8}\.history))"
    r"\.tmp\.[0-9]+\.[0-9a-f]{32}$"
)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _archive_lock(archive_root: Path):
    lock_path = archive_root / LOCK_NAME
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        opened = os.fstat(descriptor)
        published = lock_path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_gid != os.getegid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino)
            != (published.st_dev, published.st_ino)
        ):
            raise RuntimeError("WAL archive lock metadata is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = os.fstat(descriptor)
        current = lock_path.lstat()
        if (
            (locked.st_dev, locked.st_ino, locked.st_nlink)
            != (opened.st_dev, opened.st_ino, 1)
            or (current.st_dev, current.st_ino)
            != (opened.st_dev, opened.st_ino)
        ):
            raise RuntimeError("WAL archive lock changed while acquiring it")
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _hash_fd(descriptor: int, *, limit: int = MAX_ARCHIVE_BYTES) -> tuple[int, str]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    size = 0
    hasher = hashlib.sha256()
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise RuntimeError("WAL archive source is unexpectedly large")
        hasher.update(chunk)
    return size, hasher.hexdigest()


def _recover_stale_temporaries(archive_root: Path) -> None:
    temporaries = [path for path in archive_root.iterdir() if TEMP_RE.fullmatch(path.name)]
    if len(temporaries) > 128:
        raise RuntimeError("too many stale WAL archive temporary files")
    changed = False
    for temporary in temporaries:
        match = TEMP_RE.fullmatch(temporary.name)
        assert match is not None
        destination = archive_root / match.group(1)
        metadata = temporary.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_gid != os.getegid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink not in {1, 2}
        ):
            raise RuntimeError("stale WAL archive temporary metadata is unsafe")
        if metadata.st_nlink == 2:
            try:
                published = destination.lstat()
            except FileNotFoundError as exc:
                raise RuntimeError("stale WAL archive hardlink has no destination") from exc
            if (published.st_dev, published.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise RuntimeError("stale WAL archive hardlink points outside its destination")
        temporary.unlink()
        changed = True
    if changed:
        _fsync_directory(archive_root)


def _archive_wal_locked(source: Path, name: str, archive_root: Path) -> None:
    _recover_stale_temporaries(archive_root)

    source_fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    temporary = archive_root / f".{name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
    temporary_fd = -1
    try:
        source_before = os.fstat(source_fd)
        if not stat.S_ISREG(source_before.st_mode) or source_before.st_nlink != 1:
            raise RuntimeError("WAL archive source metadata is unsafe")
        if (
            source_before.st_uid != os.geteuid()
            or source_before.st_gid != os.getegid()
            or stat.S_IMODE(source_before.st_mode) != 0o600
        ):
            raise RuntimeError("WAL archive source ownership or mode is unsafe")
        temporary_fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        source_size = 0
        source_hash = hashlib.sha256()
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            source_size += len(chunk)
            if source_size > MAX_ARCHIVE_BYTES:
                raise RuntimeError("WAL archive source is unexpectedly large")
            source_hash.update(chunk)
            offset = 0
            while offset < len(chunk):
                written = os.write(temporary_fd, chunk[offset:])
                if written <= 0:
                    raise RuntimeError("WAL archive copy made no progress")
                offset += written
        source_after = os.fstat(source_fd)
        if (
            source_after.st_dev,
            source_after.st_ino,
            source_after.st_size,
            source_after.st_mtime_ns,
            source_after.st_ctime_ns,
        ) != (
            source_before.st_dev,
            source_before.st_ino,
            source_before.st_size,
            source_before.st_mtime_ns,
            source_before.st_ctime_ns,
        ) or source_size != source_before.st_size:
            raise RuntimeError("WAL archive source changed during copy")
        if WAL_SEGMENT_ARCHIVE_RE.fullmatch(name) and source_size != WAL_SEGMENT_BYTES:
            raise RuntimeError("WAL segment size is not canonical")
        os.fsync(temporary_fd)
        destination = archive_root / name
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            destination_fd = os.open(
                destination, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
            )
            try:
                destination_metadata = os.fstat(destination_fd)
                if (
                    not stat.S_ISREG(destination_metadata.st_mode)
                    or destination_metadata.st_uid != os.geteuid()
                    or destination_metadata.st_gid != os.getegid()
                    or stat.S_IMODE(destination_metadata.st_mode) != 0o600
                    or destination_metadata.st_nlink != 1
                ):
                    raise RuntimeError("existing WAL archive destination is unsafe")
                existing_size, existing_hash = _hash_fd(destination_fd)
                if WAL_SEGMENT_ARCHIVE_RE.fullmatch(name) and existing_size != WAL_SEGMENT_BYTES:
                    raise RuntimeError("existing WAL segment size is not canonical")
                if (
                    existing_size != source_size
                    or existing_hash != source_hash.hexdigest()
                ):
                    raise RuntimeError("existing WAL archive destination differs")
            finally:
                os.close(destination_fd)
        else:
            _fsync_directory(archive_root)
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        os.close(source_fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        else:
            _fsync_directory(archive_root)


def archive_wal(source: Path, name: str, *, archive_root: Path = ARCHIVE_ROOT) -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("required file protection is unavailable")
    if not ARCHIVABLE_WAL_RE.fullmatch(name) or source.name != name:
        raise RuntimeError("WAL archive name is not canonical")
    root_metadata = archive_root.lstat()
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or root_metadata.st_gid != os.getegid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RuntimeError("WAL archive directory metadata is unsafe")
    with _archive_lock(archive_root):
        _archive_wal_locked(source, name, archive_root)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2:
        print("archive WAL: expected source path and canonical WAL name", file=sys.stderr)
        return 64
    try:
        archive_wal(Path(arguments[0]), arguments[1])
    except (OSError, RuntimeError) as exc:
        print(f"archive WAL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
