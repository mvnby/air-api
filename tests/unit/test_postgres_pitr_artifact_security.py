from __future__ import annotations

import io
import stat
import tarfile
from pathlib import Path

import pytest

from scripts.ha import postgres_pitr_artifact_security as security


def _archive(path: Path, names: list[str]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            payload = name.encode("utf-8")
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))


@pytest.mark.parametrize("alias", ["./postgresql.conf", "a/../postgresql.conf"])
def test_rejects_duplicate_normalized_tar_paths(tmp_path: Path, alias: str):
    tar_path = tmp_path / "base.tar.gz"
    _archive(tar_path, ["postgresql.conf", alias])

    with pytest.raises(SystemExit, match="Duplicate normalized tar member"):
        security.safe_extract_tar_gz(
            tar_path,
            tmp_path / "data",
            max_members=10,
            max_expanded_bytes=1024,
        )


def test_rejects_normalized_path_escape_before_extraction(tmp_path: Path):
    tar_path = tmp_path / "base.tar.gz"
    _archive(tar_path, ["safe/../../outside.so"])

    with pytest.raises(SystemExit, match="Unsafe tar member path"):
        security.safe_extract_tar_gz(
            tar_path,
            tmp_path / "data",
            max_members=10,
            max_expanded_bytes=1024,
        )

    assert not (tmp_path / "outside.so").exists()


def test_extraction_ignores_untrusted_group_world_write_modes(tmp_path: Path):
    tar_path = tmp_path / "base.tar.gz"
    with tarfile.open(tar_path, "w:gz") as archive:
        directory = tarfile.TarInfo("global")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o777
        archive.addfile(directory)
        payload = b"15\n"
        member = tarfile.TarInfo("global/PG_VERSION")
        member.mode = 0o777
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    destination = tmp_path / "data"
    security.safe_extract_tar_gz(
        tar_path,
        destination,
        max_members=10,
        max_expanded_bytes=1024,
    )

    assert stat.S_IMODE((destination / "global").stat().st_mode) == 0o700
    assert stat.S_IMODE((destination / "global/PG_VERSION").stat().st_mode) == 0o600
