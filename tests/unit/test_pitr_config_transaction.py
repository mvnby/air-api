import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


transaction = _load(
    "pitr_config_transaction_receipt_tests",
    ROOT / "scripts/ha/pitr_config_transaction.py",
)
configure = _load(
    "configure_postgres_pitr_env_receipt_tests",
    ROOT / "scripts/ha/configure_postgres_pitr_env.py",
)

TXID = "0123456789abcdef0123456789abcdef"
OLD_ENV = b"POSTGRES_USER=postgres\n"
OLD_SECRETS = b"POSTGRES_PITR_S3_SECRET_ACCESS_KEY=old\n"
NEW_ENV = b"POSTGRES_USER=postgres\nPOSTGRES_PITR_ARCHIVE_MODE=off\n"
NEW_SECRETS = b"POSTGRES_PITR_S3_SECRET_ACCESS_KEY=new\n"


def _write_controlled(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(0o600)


def _case(tmp_path: Path) -> dict[str, object]:
    env_path = tmp_path / ".env"
    secrets_path = tmp_path / "pitr-secrets.env"
    _write_controlled(env_path, OLD_ENV)
    _write_controlled(secrets_path, OLD_SECRETS)
    return {
        "env_path": env_path,
        "secrets_path": secrets_path,
        "transaction_root": tmp_path / "transactions",
        "transaction_id": TXID,
        "old_env": OLD_ENV,
        "old_secrets": OLD_SECRETS,
        "new_env": NEW_ENV,
        "new_secrets": NEW_SECRETS,
        "uid": os.geteuid(),
        "gid": os.getegid(),
        "read_controlled_file": configure.read_controlled_file,
        "validate_environment": configure.validate_sanitized_environment,
    }


def _commit(case: dict[str, object], **changes: object) -> None:
    transaction.commit_split_transaction(**{**case, **changes})


def _recover(case: dict[str, object]) -> None:
    transaction.recover_split_transactions(
        **{
            key: case[key]
            for key in (
                "transaction_root",
                "env_path",
                "secrets_path",
                "uid",
                "gid",
                "read_controlled_file",
                "validate_environment",
            )
        }
    )


def _receipt_path(case: dict[str, object]) -> Path:
    root = transaction._completion_receipt_root(case["transaction_root"])
    return root / f"{TXID}.json"


def test_commit_persists_canonical_root_only_receipt_before_cleanup(tmp_path):
    case = _case(tmp_path)

    _commit(case)

    receipt_path = _receipt_path(case)
    receipt = json.loads(receipt_path.read_bytes())
    assert set(receipt) == transaction.COMPLETION_RECEIPT_KEYS
    assert receipt == {
        "schema_version": 1,
        "transaction_id": TXID,
        "env_path": str(case["env_path"]),
        "secrets_path": str(case["secrets_path"]),
        "new_env_sha256": transaction._payload_sha(NEW_ENV),
        "new_secrets_sha256": transaction._payload_sha(NEW_SECRETS),
    }
    assert receipt_path.read_bytes() == transaction._canonical_json(receipt)
    metadata = receipt_path.lstat()
    assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert metadata.st_uid == os.geteuid()
    assert metadata.st_gid == os.getegid()
    assert metadata.st_nlink == 1
    receipt_root = receipt_path.parent.lstat()
    assert stat.S_IMODE(receipt_root.st_mode) == 0o700
    assert not list(case["transaction_root"].iterdir())
    assert not list(receipt_path.parent.glob(".*.pitr-*"))


def test_same_transaction_payload_is_idempotent_without_file_mutation(tmp_path):
    case = _case(tmp_path)
    _commit(case)
    paths = (case["env_path"], case["secrets_path"], _receipt_path(case))
    before = [(path.lstat().st_ino, path.lstat().st_mtime_ns) for path in paths]

    _commit(case, old_env=NEW_ENV, old_secrets=NEW_SECRETS)

    after = [(path.lstat().st_ino, path.lstat().st_mtime_ns) for path in paths]
    assert after == before
    assert case["env_path"].read_bytes() == NEW_ENV
    assert case["secrets_path"].read_bytes() == NEW_SECRETS


@pytest.mark.parametrize(
    ("changed_key", "changed_payload"),
    (("new_env", NEW_ENV + b"CHANGED=1\n"), ("new_secrets", NEW_SECRETS + b"X=1\n")),
)
def test_same_transaction_rejects_changed_desired_payload(
    tmp_path, changed_key, changed_payload
):
    case = _case(tmp_path)
    _commit(case)
    receipt_before = _receipt_path(case).read_bytes()

    with pytest.raises(RuntimeError, match="receipt conflicts"):
        _commit(case, **{changed_key: changed_payload})

    assert _receipt_path(case).read_bytes() == receipt_before
    assert case["env_path"].read_bytes() == NEW_ENV
    assert case["secrets_path"].read_bytes() == NEW_SECRETS


@pytest.mark.parametrize("drift_key", ("env_path", "secrets_path"))
def test_same_transaction_rejects_target_file_drift(tmp_path, drift_key):
    case = _case(tmp_path)
    _commit(case)
    _write_controlled(case[drift_key], b"external-drift\n")

    with pytest.raises(RuntimeError, match="target files drifted"):
        _commit(case)

    assert case[drift_key].read_bytes() == b"external-drift\n"


def test_recovery_writes_missing_receipt_for_committed_generation(tmp_path, monkeypatch):
    case = _case(tmp_path)
    original_write = transaction._write_completion_receipt
    monkeypatch.setattr(
        transaction,
        "_write_completion_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated receipt write crash")
        ),
    )

    with pytest.raises(RuntimeError, match="simulated receipt write crash"):
        _commit(case)

    assert case["env_path"].read_bytes() == NEW_ENV
    assert case["secrets_path"].read_bytes() == NEW_SECRETS
    assert not _receipt_path(case).exists()
    assert (case["transaction_root"] / TXID / "journal.json").is_file()

    monkeypatch.setattr(transaction, "_write_completion_receipt", original_write)
    original_rmtree = transaction.shutil.rmtree

    def assert_receipt_then_remove(path, *args, **kwargs):
        assert _receipt_path(case).is_file()
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(transaction.shutil, "rmtree", assert_receipt_then_remove)
    _recover(case)

    assert _receipt_path(case).is_file()
    assert not list(case["transaction_root"].iterdir())


def test_recovery_closes_crash_window_after_receipt_before_journal_cleanup(
    tmp_path, monkeypatch
):
    case = _case(tmp_path)
    original_rmtree = transaction.shutil.rmtree
    monkeypatch.setattr(
        transaction.shutil,
        "rmtree",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated cleanup crash")
        ),
    )

    with pytest.raises(RuntimeError, match="simulated cleanup crash"):
        _commit(case)

    receipt_before = _receipt_path(case).read_bytes()
    assert (case["transaction_root"] / TXID / "journal.json").is_file()

    monkeypatch.setattr(transaction.shutil, "rmtree", original_rmtree)
    _recover(case)

    assert _receipt_path(case).read_bytes() == receipt_before
    assert not list(case["transaction_root"].iterdir())


def test_recovery_fails_closed_if_receipted_generation_drifted(tmp_path, monkeypatch):
    case = _case(tmp_path)
    original_rmtree = transaction.shutil.rmtree
    monkeypatch.setattr(
        transaction.shutil,
        "rmtree",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("cleanup crash")),
    )
    with pytest.raises(RuntimeError, match="cleanup crash"):
        _commit(case)
    monkeypatch.setattr(transaction.shutil, "rmtree", original_rmtree)
    _write_controlled(case["env_path"], b"external-drift\n")

    with pytest.raises(RuntimeError, match="ambiguous target generations"):
        _recover(case)

    assert _receipt_path(case).is_file()
    assert (case["transaction_root"] / TXID).is_dir()


@pytest.mark.parametrize("attack", ("hardlink", "symlink", "mode"))
def test_receipt_metadata_attacks_fail_closed(tmp_path, attack):
    case = _case(tmp_path)
    _commit(case)
    receipt_path = _receipt_path(case)
    if attack == "hardlink":
        os.link(receipt_path, receipt_path.parent / "receipt-hardlink")
    elif attack == "symlink":
        target = receipt_path.parent / "receipt-target"
        receipt_path.rename(target)
        receipt_path.symlink_to(target)
    else:
        receipt_path.chmod(0o640)

    with pytest.raises(RuntimeError, match="receipt metadata is unsafe"):
        _commit(case)


def test_receipt_ownership_mismatch_fails_closed(tmp_path, monkeypatch):
    case = _case(tmp_path)
    _commit(case)
    receipt_path = _receipt_path(case)
    original_lstat = Path.lstat

    def mismatched_owner(path):
        metadata = original_lstat(path)
        if path == receipt_path:
            values = list(metadata)
            values[4] = metadata.st_uid + 1
            return os.stat_result(values)
        return metadata

    monkeypatch.setattr(Path, "lstat", mismatched_owner)
    with pytest.raises(RuntimeError, match="receipt metadata is unsafe"):
        _commit(case)


def test_noncanonical_or_conflicting_receipt_fails_closed(tmp_path):
    case = _case(tmp_path)
    _commit(case)
    receipt_path = _receipt_path(case)
    receipt = json.loads(receipt_path.read_bytes())
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="ascii")
    receipt_path.chmod(0o600)
    with pytest.raises(RuntimeError, match="not canonical"):
        _commit(case)

    receipt["new_env_sha256"] = "f" * 64
    receipt_path.write_bytes(transaction._canonical_json(receipt))
    receipt_path.chmod(0o600)
    with pytest.raises(RuntimeError, match="receipt conflicts"):
        _commit(case)


def test_unsafe_receipt_root_is_rejected_even_without_open_transaction(tmp_path):
    case = _case(tmp_path)
    _commit(case)
    receipt_root = _receipt_path(case).parent
    receipt_root.chmod(0o755)

    with pytest.raises(RuntimeError, match="receipt root metadata is unsafe"):
        _recover(case)
