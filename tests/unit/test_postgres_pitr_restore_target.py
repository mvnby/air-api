import json
from pathlib import Path

import pytest

from tests.unit import postgres_pitr_restore_test_support as support

pitr_restore = support.pitr_restore
TARGET_NAME = "mvn_pitr_" + "b" * 32


def _named_args(target_dir: Path, *, target_lsn: str = "0/900") -> list[str]:
    args = support._prepare_args(target_dir)
    time_index = args.index("--target-time")
    del args[time_index : time_index + 2]
    args.extend(["--target-name", TARGET_NAME, "--target-lsn", target_lsn])
    return args


def test_prepare_writes_exact_named_restore_point_and_lsn(monkeypatch, tmp_path):
    objects, _ = support._restore_objects()
    monkeypatch.setattr(pitr_restore, "load_config", lambda: support.FakeConfig)
    monkeypatch.setattr(
        pitr_restore,
        "build_client",
        lambda _config: support.FakeClient(objects),
    )

    target_dir = tmp_path / "restore"
    assert pitr_restore.main(_named_args(target_dir)) == 0

    safe_conf = (target_dir / "control/postgresql.conf").read_text()
    assert "recovery_target_name = '" + TARGET_NAME + "'" in safe_conf
    assert "recovery_target_inclusive = on" in safe_conf
    contract = json.loads((target_dir / "restore-contract.json").read_text())
    assert contract["target_mode"] == "name"
    assert contract["target_name"] == TARGET_NAME
    assert contract["target_lsn"] == "0/900"
    assert contract["target_time"] == ""


def test_named_target_lsn_must_follow_completed_basebackup(monkeypatch, tmp_path):
    objects, _ = support._restore_objects()
    monkeypatch.setattr(pitr_restore, "load_config", lambda: support.FakeConfig)
    monkeypatch.setattr(
        pitr_restore,
        "build_client",
        lambda _config: support.FakeClient(objects),
    )

    with pytest.raises(SystemExit, match="target LSN precedes"):
        pitr_restore.main(_named_args(tmp_path / "restore", target_lsn="0/700"))


def test_restore_target_selector_is_mutually_exclusive(tmp_path):
    args = support._prepare_args(tmp_path / "restore")
    args.extend(["--target-name", TARGET_NAME, "--target-lsn", "0/900"])

    with pytest.raises(SystemExit, match="either target time or target name"):
        pitr_restore.main(args)
