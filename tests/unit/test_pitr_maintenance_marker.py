import os
from pathlib import Path

import pytest

from scripts.ha import verify_pitr_maintenance_marker as marker_attestation


TRANSACTION_ID = "a" * 32


def _marker(path: Path, value: str = TRANSACTION_ID) -> Path:
    path.write_text(f"{value}\n", encoding="ascii")
    path.chmod(0o600)
    return path


def _verify(path: Path, transaction_id: str = TRANSACTION_ID) -> None:
    marker_attestation.verify_marker(
        str(path),
        transaction_id,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )


def test_marker_attestation_accepts_exact_transaction_and_metadata(tmp_path):
    _verify(_marker(tmp_path / "maintenance"))


@pytest.mark.parametrize(
    ("value", "transaction_id"),
    [
        ("b" * 32, TRANSACTION_ID),
        (TRANSACTION_ID, "A" * 32),
        (TRANSACTION_ID, "short"),
    ],
)
def test_marker_attestation_rejects_wrong_or_invalid_transaction(
    tmp_path, value, transaction_id
):
    path = _marker(tmp_path / "maintenance", value)

    with pytest.raises(RuntimeError):
        _verify(path, transaction_id)


def test_marker_attestation_rejects_wrong_mode_symlink_and_hardlink(tmp_path):
    wrong_mode = _marker(tmp_path / "wrong-mode")
    wrong_mode.chmod(0o640)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        _verify(wrong_mode)

    target = _marker(tmp_path / "target")
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        _verify(symlink)

    hardlink = tmp_path / "hardlink"
    os.link(target, hardlink)
    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        _verify(target)


def test_marker_attestation_rejects_path_replacement_during_read(
    tmp_path, monkeypatch
):
    path = _marker(tmp_path / "maintenance")
    replacement = _marker(tmp_path / "replacement")
    real_read = marker_attestation.os.read

    def replace_after_read(descriptor: int, size: int) -> bytes:
        content = real_read(descriptor, size)
        os.replace(replacement, path)
        return content

    monkeypatch.setattr(marker_attestation.os, "read", replace_after_read)
    with pytest.raises(RuntimeError, match="changed"):
        _verify(path)


def test_cli_is_fixed_to_canonical_root_owned_marker():
    source = Path(marker_attestation.__file__).read_text(encoding="utf-8")

    assert marker_attestation.MARKER_PATH == "/run/mvn-postgres-pitr-maintenance"
    assert marker_attestation.PINNED_VALIDATOR == (
        "/usr/local/libexec/mvn-pitr/verify_pitr_maintenance_marker.py"
    )
    assert "verify_marker(MARKER_PATH, sys.argv[2])" in source
    assert "verify_pinned_runtime(tuple(sys.argv[3:]))" in source
    assert "expected_uid: int = 0" in source
    assert "expected_gid: int = 0" in source
    assert "os.O_NOFOLLOW" in source
