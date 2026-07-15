import os
import time
from pathlib import Path

import pytest

from scripts.ha import (
    pitr_completion_attestation,
    pitr_remote_asset_attestation,
    pitr_remote_execution,
)


TXID = "0123456789abcdef0123456789abcdef"
NONCE = "fedcba9876543210fedcba9876543210"
WRAPPER_DIGEST = "a" * 64
FIELDS = (
    NONCE,
    TXID,
    "configure-node",
    "/opt/mvn-reserve",
    "docker-compose.patroni.yml",
    '{"asset":"digest"}',
    WRAPPER_DIGEST,
)


def _namespace(tmp_path: Path):
    namespace = {}
    source = (
        pitr_remote_asset_attestation.REMOTE_ASSET_ATTESTATION
        + "\n"
        + pitr_completion_attestation.REMOTE_COMPLETION_ATTESTATION
    )
    exec(compile(source, "<pitr-completion-attestation>", "exec"), namespace)
    namespace["COMPLETION_ROOT"] = str(tmp_path / "receipts")
    namespace["COMPLETION_UID"] = os.geteuid()
    namespace["COMPLETION_GID"] = os.getegid()
    return namespace


def test_completion_receipt_is_exact_atomic_and_consumed(tmp_path):
    namespace = _namespace(tmp_path)

    namespace["write_completion_receipt"](*FIELDS)
    receipt = tmp_path / "receipts" / f"{NONCE}.json"

    assert receipt.is_file()
    assert receipt.stat().st_mode & 0o777 == 0o600
    namespace["consume_completion_receipt"](*FIELDS)
    assert not receipt.exists()


def test_zero_status_without_completion_receipt_fails_closed(tmp_path):
    namespace = _namespace(tmp_path)

    with pytest.raises(FileNotFoundError):
        namespace["consume_completion_after_status"](0, *FIELDS)


def test_nonzero_status_never_accepts_or_writes_a_completion(tmp_path):
    namespace = _namespace(tmp_path)

    assert namespace["write_completion_after_status"](1, *FIELDS) == 1
    assert namespace["consume_completion_after_status"](1, *FIELDS) == 1
    assert not (tmp_path / "receipts").exists()


def test_tampered_completion_receipt_is_rejected(tmp_path):
    namespace = _namespace(tmp_path)
    namespace["write_completion_receipt"](*FIELDS)
    receipt = tmp_path / "receipts" / f"{NONCE}.json"
    payload = receipt.read_bytes()
    receipt.write_bytes(payload.replace(b"configure-node", b"configure-nodf"))
    receipt.chmod(0o600)

    with pytest.raises(RuntimeError, match="content is invalid"):
        namespace["consume_completion_receipt"](*FIELDS)


def test_inline_completion_hardening_is_not_part_of_host_release_bundle():
    bundled_names = {
        asset.source.name for asset in pitr_remote_execution.PITR_HOST_ASSETS
    }

    assert "pitr_completion_attestation.py" not in bundled_names
    assert "pitr_remote_asset_attestation.py" not in bundled_names
    assert "pitr_remote_executors.py" not in bundled_names


def test_stale_receipt_and_partial_temporary_are_scavenged(tmp_path):
    namespace = _namespace(tmp_path)
    namespace["write_completion_receipt"](*FIELDS)
    root = tmp_path / "receipts"
    receipt = root / f"{NONCE}.json"
    temporary = root / f".{NONCE}.123.tmp"
    temporary.write_bytes(b"partial")
    temporary.chmod(0o600)
    old = time.time_ns() - namespace["COMPLETION_STALE_AFTER_NS"] - 1
    os.utime(receipt, ns=(old, old))
    os.utime(temporary, ns=(old, old))

    assert namespace["scavenge_completion_receipts"]() == 2
    assert list(root.iterdir()) == []


def test_recent_receipt_is_preserved_for_its_outer_executor(tmp_path):
    namespace = _namespace(tmp_path)
    namespace["write_completion_receipt"](*FIELDS)
    receipt = tmp_path / "receipts" / f"{NONCE}.json"

    assert namespace["scavenge_completion_receipts"]() == 0
    assert receipt.exists()
    assert namespace["discard_completion_receipt"](*FIELDS) is True
    assert namespace["discard_completion_receipt"](*FIELDS) is False


def test_scavenger_rejects_symlinked_and_hardlinked_entries(tmp_path):
    symlink_namespace = _namespace(tmp_path / "symlink-case")
    symlink_root = Path(symlink_namespace["COMPLETION_ROOT"])
    symlink_root.mkdir(mode=0o700, parents=True)
    (symlink_root / f"{NONCE}.json").symlink_to("/dev/null")

    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        symlink_namespace["scavenge_completion_receipts"]()

    hardlink_parent = tmp_path / "hardlink-case"
    hardlink_parent.mkdir()
    hardlink_namespace = _namespace(hardlink_parent)
    hardlink_namespace["write_completion_receipt"](*FIELDS)
    hardlink_root = Path(hardlink_namespace["COMPLETION_ROOT"])
    receipt = hardlink_root / f"{NONCE}.json"
    os.link(receipt, hardlink_root / f"{'1' * 32}.json")

    with pytest.raises(RuntimeError, match="metadata is unsafe"):
        hardlink_namespace["scavenge_completion_receipts"]()


def test_recent_receipt_cap_requires_bounded_retry_not_manual_cleanup(tmp_path):
    namespace = _namespace(tmp_path)
    root = Path(namespace["COMPLETION_ROOT"])
    root.mkdir(mode=0o700)
    for index in range(64):
        nonce = f"{index:032x}"
        fields = (nonce, *FIELDS[1:])
        namespace["write_completion_receipt"](*fields)

    with pytest.raises(RuntimeError, match="bounded retry"):
        namespace["scavenge_completion_receipts"]()
