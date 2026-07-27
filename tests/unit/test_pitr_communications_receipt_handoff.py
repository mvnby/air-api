import stat
from pathlib import Path

import pytest

from tests.unit.test_pitr_bundle_transport import (
    TXID,
    _payload,
    _remote_namespace,
    _write,
)


def _seed_preflight_receipt(namespace, project):
    marker = Path(namespace["MAINTENANCE_MARKER"])
    _write(marker, (TXID + "\n").encode("ascii"), 0o600)
    receipt = project / ".ha-communications-cutover-preflight"
    _write(
        receipt,
        f"communications-off-drained-v1\n{TXID}\n".encode("ascii"),
        0o600,
    )
    fence = project / ".ha-communications-worker-release-fenced"
    _write(fence, b"fenced\n", 0o600)
    return marker, receipt, fence


def test_preflight_receipt_hands_off_to_apply_and_finalize(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    marker, receipt, fence = _seed_preflight_receipt(namespace, project)

    assert namespace["execute"](
        "inspect", TXID, str(project), compose.name, payload
    ) == "preflight-fenced"
    assert namespace["execute"](
        "apply", TXID, str(project), compose.name, payload
    ) == "applied"
    assert receipt.exists()
    assert namespace["execute"](
        "finalize", TXID, str(project), compose.name, b""
    ) == "finalized"

    assert not marker.exists()
    assert not receipt.exists()
    assert fence.read_bytes() == b"fenced\n"
    assert stat.S_IMODE(fence.stat().st_mode) == 0o600


@pytest.mark.parametrize("damage", ["missing-fence", "unsafe-receipt"])
def test_preflight_receipt_handoff_rejects_incomplete_or_unsafe_proof(
    tmp_path, damage
):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    marker, receipt, fence = _seed_preflight_receipt(namespace, project)
    if damage == "missing-fence":
        fence.unlink()
    else:
        receipt.chmod(0o644)

    with pytest.raises(RuntimeError):
        namespace["execute"](
            "inspect", TXID, str(project), compose.name, payload
        )

    assert marker.read_text(encoding="ascii") == TXID + "\n"
    assert receipt.exists()


def test_preflight_receipt_is_removed_on_owned_bundle_rollback(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    marker, receipt, fence = _seed_preflight_receipt(namespace, project)

    assert namespace["execute"](
        "apply", TXID, str(project), compose.name, payload
    ) == "applied"
    assert namespace["execute"](
        "rollback", TXID, str(project), compose.name, b""
    ) == "rolled-back"

    assert not marker.exists()
    assert not receipt.exists()
    assert fence.read_bytes() == b"fenced\n"


def test_finalize_crash_after_marker_unlink_replays_receipt_cleanup(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    marker, receipt, fence = _seed_preflight_receipt(namespace, project)
    assert namespace["execute"](
        "apply", TXID, str(project), compose.name, payload
    ) == "applied"

    fsync_paths = []
    real_fsync = namespace["fsync_dir"]
    real_remove_receipt = namespace["remove_communications_cutover_receipt"]

    def recording_fsync(path):
        fsync_paths.append(path)
        real_fsync(path)

    def crash_after_marker(project_dir, txid):
        assert project_dir == str(project)
        assert txid == TXID
        assert not marker.exists()
        assert receipt.exists()
        raise RuntimeError("injected crash after marker unlink")

    namespace["fsync_dir"] = recording_fsync
    namespace["remove_communications_cutover_receipt"] = crash_after_marker
    with pytest.raises(RuntimeError, match="injected crash"):
        namespace["execute"](
            "finalize", TXID, str(project), compose.name, b""
        )

    assert not marker.exists()
    assert receipt.exists()
    assert str(marker.parent) in fsync_paths
    namespace["remove_communications_cutover_receipt"] = real_remove_receipt
    assert namespace["execute"](
        "finalize", TXID, str(project), compose.name, b""
    ) == "already-finalized"
    assert not receipt.exists()
    assert str(project) in fsync_paths
    assert fence.read_bytes() == b"fenced\n"


def test_rollback_crash_after_marker_unlink_replays_receipt_cleanup(tmp_path):
    namespace, project, compose, tool = _remote_namespace(tmp_path)
    _write(compose, b"old-compose", 0o644)
    _write(tool, b"old-tool", 0o755)
    payload, _ = _payload(namespace, project, compose, tool)
    marker, receipt, fence = _seed_preflight_receipt(namespace, project)
    assert namespace["execute"](
        "apply", TXID, str(project), compose.name, payload
    ) == "applied"

    fsync_paths = []
    real_fsync = namespace["fsync_dir"]
    real_remove_receipt = namespace["remove_communications_cutover_receipt"]

    def recording_fsync(path):
        fsync_paths.append(path)
        real_fsync(path)

    def crash_after_marker(project_dir, txid):
        assert project_dir == str(project)
        assert txid == TXID
        assert not marker.exists()
        assert receipt.exists()
        raise RuntimeError("injected crash after marker unlink")

    namespace["fsync_dir"] = recording_fsync
    namespace["remove_communications_cutover_receipt"] = crash_after_marker
    with pytest.raises(RuntimeError, match="injected crash"):
        namespace["execute"](
            "rollback", TXID, str(project), compose.name, b""
        )

    assert not marker.exists()
    assert receipt.exists()
    assert str(marker.parent) in fsync_paths
    namespace["remove_communications_cutover_receipt"] = real_remove_receipt
    assert namespace["execute"](
        "rollback", TXID, str(project), compose.name, b""
    ) == "already-rolled-back"
    assert not receipt.exists()
    assert str(project) in fsync_paths
    assert fence.read_bytes() == b"fenced\n"
