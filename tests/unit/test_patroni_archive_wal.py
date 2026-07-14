import importlib.util
import os
import stat
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "deploy/ha/patroni/archive_wal.py"
)
SPEC = importlib.util.spec_from_file_location("patroni_archive_wal", MODULE_PATH)
assert SPEC and SPEC.loader
archive = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = archive
SPEC.loader.exec_module(archive)


def _directories(tmp_path: Path) -> tuple[Path, Path]:
    source_root = tmp_path / "source"
    archive_root = tmp_path / "archive"
    source_root.mkdir(mode=0o700)
    archive_root.mkdir(mode=0o700)
    return source_root, archive_root


def _source(source_root: Path, name: str, payload: bytes) -> Path:
    path = source_root / name
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def test_archives_history_file_durably_and_replays_identical_source(tmp_path):
    source_root, archive_root = _directories(tmp_path)
    source = _source(source_root, "00000002.history", b"timeline-history\n")

    archive.archive_wal(source, source.name, archive_root=archive_root)
    archive.archive_wal(source, source.name, archive_root=archive_root)

    destination = archive_root / source.name
    assert destination.read_bytes() == b"timeline-history\n"
    metadata = destination.lstat()
    assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert metadata.st_nlink == 1
    assert (archive_root / archive.LOCK_NAME).is_file()
    assert not [path for path in archive_root.iterdir() if archive.TEMP_RE.fullmatch(path.name)]


def test_archives_canonical_16_mib_segment_with_bounded_latency(tmp_path):
    source_root, archive_root = _directories(tmp_path)
    name = "00000001000000000000000A"
    source = source_root / name
    with source.open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    source.chmod(0o600)

    started = time.monotonic()
    archive.archive_wal(source, name, archive_root=archive_root)

    assert (archive_root / name).stat().st_size == 16 * 1024 * 1024
    assert time.monotonic() - started < 10


def test_rejects_noncanonical_segment_size(tmp_path):
    source_root, archive_root = _directories(tmp_path)
    name = "00000001000000000000000A"
    source = _source(source_root, name, b"too-small")

    with pytest.raises(RuntimeError, match="segment size is not canonical"):
        archive.archive_wal(source, name, archive_root=archive_root)

    assert not (archive_root / name).exists()


def test_rejects_source_with_noncanonical_mode(tmp_path):
    source_root, archive_root = _directories(tmp_path)
    source = _source(source_root, "00000002.history", b"history")
    source.chmod(0o644)

    with pytest.raises(RuntimeError, match="ownership or mode is unsafe"):
        archive.archive_wal(source, source.name, archive_root=archive_root)


def test_existing_collision_must_have_identical_content(tmp_path):
    source_root, archive_root = _directories(tmp_path)
    source = _source(source_root, "00000002.history", b"new")
    destination = archive_root / source.name
    destination.write_bytes(b"old")
    destination.chmod(0o600)

    with pytest.raises(RuntimeError, match="destination differs"):
        archive.archive_wal(source, source.name, archive_root=archive_root)

    assert destination.read_bytes() == b"old"


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_rejects_linked_source(tmp_path, kind):
    source_root, archive_root = _directories(tmp_path)
    name = "00000002.history"
    original = _source(source_root, "original", b"history")
    source = source_root / name
    if kind == "symlink":
        source.symlink_to(original)
        expected = OSError
    else:
        os.link(original, source)
        expected = RuntimeError

    with pytest.raises(expected):
        archive.archive_wal(source, name, archive_root=archive_root)


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_rejects_linked_existing_destination(tmp_path, kind):
    source_root, archive_root = _directories(tmp_path)
    source = _source(source_root, "00000002.history", b"history")
    original = archive_root / "original"
    original.write_bytes(b"history")
    original.chmod(0o600)
    destination = archive_root / source.name
    if kind == "symlink":
        destination.symlink_to(original)
        expected = OSError
    else:
        os.link(original, destination)
        expected = RuntimeError

    with pytest.raises(expected):
        archive.archive_wal(source, source.name, archive_root=archive_root)


def test_recovers_unpublished_and_published_stale_temporaries(tmp_path):
    source_root, archive_root = _directories(tmp_path)
    unpublished = archive_root / f".00000002.history.tmp.123.{'a' * 32}"
    unpublished.write_bytes(b"stale")
    unpublished.chmod(0o600)
    published_temp = archive_root / f".00000003.history.tmp.124.{'b' * 32}"
    published_temp.write_bytes(b"published")
    published_temp.chmod(0o600)
    published = archive_root / "00000003.history"
    os.link(published_temp, published)
    source = _source(source_root, "00000004.history", b"next")

    archive.archive_wal(source, source.name, archive_root=archive_root)

    assert not unpublished.exists()
    assert not published_temp.exists()
    assert published.read_bytes() == b"published"
    assert published.stat().st_nlink == 1


def test_rejects_unsafe_stale_temporary(tmp_path):
    source_root, archive_root = _directories(tmp_path)
    stale = archive_root / f".00000002.history.tmp.123.{'a' * 32}"
    stale.write_bytes(b"unsafe")
    stale.chmod(0o644)
    source = _source(source_root, "00000003.history", b"next")

    with pytest.raises(RuntimeError, match="temporary metadata is unsafe"):
        archive.archive_wal(source, source.name, archive_root=archive_root)


def test_global_lock_serializes_concurrent_archives(tmp_path, monkeypatch):
    source_root, archive_root = _directories(tmp_path)
    sources = [
        _source(source_root, "00000002.history", b"two"),
        _source(source_root, "00000003.history", b"three"),
    ]
    guard = threading.Lock()
    active = 0
    maximum = 0

    def observed_recovery(_root):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with guard:
            active -= 1

    monkeypatch.setattr(archive, "_recover_stale_temporaries", observed_recovery)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda source: archive.archive_wal(
                    source, source.name, archive_root=archive_root
                ),
                sources,
            )
        )

    assert maximum == 1
    assert all((archive_root / source.name).is_file() for source in sources)


def test_rejects_hardlinked_lock_file(tmp_path):
    source_root, archive_root = _directories(tmp_path)
    lock_path = archive_root / archive.LOCK_NAME
    lock_path.write_bytes(b"")
    lock_path.chmod(0o600)
    os.link(lock_path, archive_root / "other-lock-link")
    source = _source(source_root, "00000002.history", b"history")

    with pytest.raises(RuntimeError, match="lock metadata is unsafe"):
        archive.archive_wal(source, source.name, archive_root=archive_root)
