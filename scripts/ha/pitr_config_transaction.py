#!/usr/bin/env python3
"""Crash-safe two-file transaction used by the PITR configuration splitter."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Callable, Mapping, NamedTuple


ReadControlledFile = Callable[..., bytes]
ValidateEnvironment = Callable[[bytes], None]

JOURNAL_KEYS = frozenset(
    "transaction_id env_path secrets_path state old_env_sha256 old_secrets_sha256 "
    "old_secrets_present new_env_sha256 new_secrets_sha256 error".split()
)
COMPLETION_RECEIPT_KEYS = frozenset(
    "schema_version transaction_id env_path secrets_path new_env_sha256 "
    "new_secrets_sha256".split()
)
COMPLETION_RECEIPT_SCHEMA_VERSION = 1
MAX_COMPLETION_RECEIPT_BYTES = 4096


class ReceiptContext(NamedTuple):
    transaction_root: Path
    env_path: Path
    secrets_path: Path
    uid: int
    gid: int
    read_controlled_file: ReadControlledFile


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise RuntimeError("PITR transaction directory changed while opening")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical_json(value: Mapping[str, object]) -> bytes:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return (rendered + "\n").encode("ascii")


def _completion_receipt_root(transaction_root: Path) -> Path:
    return transaction_root.parent / f"{transaction_root.name}-receipts"


def _controlled_directory(
    path: Path, *, uid: int, gid: int, label: str, create: bool
) -> bool:
    if create:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != uid
        or metadata.st_gid != gid
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError(f"{label} metadata is unsafe")
    return True


def _completion_receipt_record(
    context: ReceiptContext, *, transaction_id: str,
    new_env_sha256: str, new_secrets_sha256: str,
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": COMPLETION_RECEIPT_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "env_path": str(context.env_path),
        "secrets_path": str(context.secrets_path),
        "new_env_sha256": new_env_sha256,
        "new_secrets_sha256": new_secrets_sha256,
    }
    _validate_completion_receipt_record(context, record, transaction_id=transaction_id)
    return record


def _validate_completion_receipt_record(
    context: ReceiptContext, record: object, *, transaction_id: str
) -> None:
    if (
        not isinstance(record, dict)
        or set(record) != COMPLETION_RECEIPT_KEYS
        or type(record["schema_version"]) is not int
        or record["schema_version"] != COMPLETION_RECEIPT_SCHEMA_VERSION
        or record["transaction_id"] != transaction_id
        or record["env_path"] != str(context.env_path)
        or record["secrets_path"] != str(context.secrets_path)
        or not all(
            isinstance(record[key], str)
            for key in COMPLETION_RECEIPT_KEYS - {"schema_version"}
        )
        or not re.fullmatch(r"[0-9a-f]{32}", transaction_id)
        or not re.fullmatch(r"[0-9a-f]{64}", record["new_env_sha256"])
        or not re.fullmatch(r"[0-9a-f]{64}", record["new_secrets_sha256"])
    ):
        raise RuntimeError("PITR completion receipt contract is invalid")


def _read_completion_receipt(
    context: ReceiptContext, transaction_id: str
) -> dict[str, object] | None:
    receipt_root = _completion_receipt_root(context.transaction_root)
    if not _controlled_directory(
        receipt_root,
        uid=context.uid,
        gid=context.gid,
        label="PITR completion receipt root",
        create=False,
    ):
        return None
    receipt_path = receipt_root / f"{transaction_id}.json"
    try:
        metadata = receipt_path.lstat()
    except FileNotFoundError:
        return None
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != context.uid
        or metadata.st_gid != context.gid
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise RuntimeError("PITR completion receipt metadata is unsafe")
    payload = context.read_controlled_file(
        receipt_path,
        label="PITR completion receipt",
        required=True,
        expected_uid=context.uid,
        exact_mode=0o600,
    )
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink")
    finished = receipt_path.lstat()
    if tuple(getattr(metadata, key) for key in fields) != tuple(
        getattr(finished, key) for key in fields
    ):
        raise RuntimeError("PITR completion receipt changed while being read")
    if len(payload) > MAX_COMPLETION_RECEIPT_BYTES:
        raise RuntimeError("PITR completion receipt is unexpectedly large")
    try:
        record = json.loads(payload)
    except (TypeError, UnicodeError, ValueError) as exc:
        raise RuntimeError("PITR completion receipt is invalid") from exc
    _validate_completion_receipt_record(context, record, transaction_id=transaction_id)
    if payload != _canonical_json(record):
        raise RuntimeError("PITR completion receipt is not canonical")
    return record


def _write_completion_receipt(
    context: ReceiptContext, record: Mapping[str, object]
) -> None:
    transaction_id = str(record.get("transaction_id", ""))
    _validate_completion_receipt_record(context, record, transaction_id=transaction_id)
    receipt_root = _completion_receipt_root(context.transaction_root)
    if not _controlled_directory(
        receipt_root,
        uid=context.uid,
        gid=context.gid,
        label="PITR completion receipt root",
        create=True,
    ):
        raise RuntimeError("could not create PITR completion receipt root")
    existing = _read_completion_receipt(context, transaction_id)
    if existing is not None:
        if existing != dict(record):
            raise RuntimeError("PITR completion receipt conflicts with this transaction")
        return
    receipt_path = receipt_root / f"{transaction_id}.json"
    staged = _write_staged(
        receipt_path,
        _canonical_json(record),
        uid=context.uid,
        gid=context.gid,
    )
    try:
        try:
            unexpected = receipt_path.lstat()
        except FileNotFoundError:
            unexpected = None
        if unexpected is not None:
            raise RuntimeError("PITR completion receipt appeared concurrently")
        os.replace(staged, receipt_path)
        _fsync_directory(receipt_root)
    finally:
        staged.unlink(missing_ok=True)
    written = _read_completion_receipt(context, transaction_id)
    if written != dict(record):
        raise RuntimeError("PITR completion receipt postcondition failed")


def _write_staged(
    path: Path,
    payload: bytes,
    *,
    uid: int,
    gid: int,
    suffix: str | None = None,
) -> Path:
    if suffix is None:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{path.name}.pitr-", dir=path.parent
        )
        staged = Path(raw_path)
    else:
        if not re.fullmatch(r"[0-9a-f]{32}", suffix):
            raise RuntimeError("PITR stage suffix is invalid")
        staged = path.parent / f".{path.name}.pitr-{suffix}"
        descriptor = os.open(
            staged,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("could not stage PITR transaction file")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, uid, gid)
        os.fsync(descriptor)
        _fsync_directory(path.parent)
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _write_new_controlled(path: Path, payload: bytes, *, uid: int, gid: int) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("PITR transaction journal write made no progress")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, uid, gid)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_journal(
    transaction_dir: Path,
    journal: Mapping[str, object],
    *,
    uid: int,
    gid: int,
) -> None:
    path = transaction_dir / "journal.json"
    payload = (json.dumps(journal, sort_keys=True, separators=(",", ":")) + "\n").encode()
    staged = _write_staged(path, payload, uid=uid, gid=gid)
    os.replace(staged, path)
    _fsync_directory(transaction_dir)


def _restore_target(path: Path, payload: bytes | None, *, uid: int, gid: int) -> None:
    if payload is None:
        path.unlink(missing_ok=True)
        _fsync_directory(path.parent)
        return
    staged = _write_staged(path, payload, uid=uid, gid=gid)
    os.replace(staged, path)
    _fsync_directory(path.parent)


def _prepare_transaction_dir(
    root: Path, transaction_id: str, *, expected_uid: int, expected_gid: int
) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise RuntimeError("PITR transaction ID is invalid")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _controlled_directory(
        root,
        uid=expected_uid,
        gid=expected_gid,
        label="PITR transaction root",
        create=False,
    )
    transaction_dir = root / transaction_id
    transaction_dir.mkdir(mode=0o700)
    metadata = transaction_dir.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != expected_uid
        or metadata.st_gid != expected_gid
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("PITR transaction directory metadata is unsafe")
    _fsync_directory(root)
    return transaction_dir


def _payload_sha(payload: bytes | None) -> str:
    return "absent" if payload is None else hashlib.sha256(payload).hexdigest()


def recover_split_transactions(
    *,
    transaction_root: Path,
    env_path: Path,
    secrets_path: Path,
    uid: int,
    gid: int,
    read_controlled_file: ReadControlledFile,
    validate_environment: ValidateEnvironment,
) -> None:
    receipt_context = ReceiptContext(
        transaction_root, env_path, secrets_path, uid, gid, read_controlled_file
    )
    _controlled_directory(
        _completion_receipt_root(transaction_root),
        uid=uid,
        gid=gid,
        label="PITR completion receipt root",
        create=False,
    )
    try:
        root_metadata = transaction_root.lstat()
    except FileNotFoundError:
        return
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != uid
        or root_metadata.st_gid != gid
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RuntimeError("PITR transaction root metadata is unsafe")
    entries = sorted(transaction_root.iterdir())
    if len(entries) > 16:
        raise RuntimeError("too many unfinished PITR split transactions")
    for transaction_dir in entries:
        metadata = transaction_dir.lstat()
        if (
            not re.fullmatch(r"[0-9a-f]{32}", transaction_dir.name)
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != uid
            or metadata.st_gid != gid
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise RuntimeError("PITR transaction directory metadata is unsafe")
        journal_path = transaction_dir / "journal.json"
        if not journal_path.exists():
            if any(transaction_dir.iterdir()):
                raise RuntimeError("unfinished PITR transaction has no journal")
            transaction_dir.rmdir()
            _fsync_directory(transaction_root)
            continue
        journal_payload = read_controlled_file(
            journal_path,
            label="PITR transaction journal",
            required=True,
            expected_uid=uid,
            exact_mode=0o600,
        )
        try:
            journal = json.loads(journal_payload)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("PITR transaction journal is invalid") from exc
        if not isinstance(journal, dict) or set(journal) != JOURNAL_KEYS:
            raise RuntimeError("PITR transaction journal schema is invalid")
        if journal_payload != _canonical_json(journal):
            raise RuntimeError("PITR transaction journal is not canonical")
        if (
            journal["transaction_id"] != transaction_dir.name
            or journal["env_path"] != str(env_path)
            or journal["secrets_path"] != str(secrets_path)
            or type(journal["old_secrets_present"]) is not bool
            or not all(
                isinstance(journal[key], str)
                for key in JOURNAL_KEYS - {"old_secrets_present"}
            )
        ):
            raise RuntimeError("PITR transaction journal target is invalid")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", journal["old_env_sha256"])
            or not re.fullmatch(r"[0-9a-f]{64}", journal["new_env_sha256"])
            or not re.fullmatch(r"[0-9a-f]{64}", journal["new_secrets_sha256"])
            or (
                journal["old_secrets_present"]
                and not re.fullmatch(r"[0-9a-f]{64}", journal["old_secrets_sha256"])
            )
            or (
                not journal["old_secrets_present"]
                and journal["old_secrets_sha256"] != "absent"
            )
        ):
            raise RuntimeError("PITR transaction journal digest contract is invalid")
        receipt = _read_completion_receipt(receipt_context, transaction_dir.name)
        if journal["state"] == "initializing":
            if receipt is not None:
                raise RuntimeError(
                    "initializing PITR transaction unexpectedly has a completion receipt"
                )
            for candidate in (
                env_path.parent / f".{env_path.name}.pitr-{transaction_dir.name}",
                secrets_path.parent / f".{secrets_path.name}.pitr-{transaction_dir.name}",
            ):
                candidate.unlink(missing_ok=True)
            shutil.rmtree(transaction_dir)
            _fsync_directory(transaction_root)
            continue
        original_env = read_controlled_file(
            transaction_dir / "original-project.env",
            label="PITR transaction project snapshot",
            required=True,
            expected_uid=uid,
            exact_mode=0o600,
        )
        original_secrets = None
        if journal["old_secrets_present"]:
            original_secrets = read_controlled_file(
                transaction_dir / "original-secrets.env",
                label="PITR transaction secrets snapshot",
                required=True,
                expected_uid=uid,
                exact_mode=0o600,
            )
        if (
            _payload_sha(original_env) != journal["old_env_sha256"]
            or _payload_sha(original_secrets) != journal["old_secrets_sha256"]
        ):
            raise RuntimeError("PITR transaction snapshot digest mismatch")
        current_env = read_controlled_file(
            env_path,
            label="project env during PITR recovery",
            required=True,
            expected_uid=uid,
            exact_mode=0o600,
        )
        current_secrets_exists = secrets_path.exists()
        current_secrets = read_controlled_file(
            secrets_path,
            label="PITR secrets during recovery",
            required=False,
            expected_uid=uid,
            exact_mode=0o600,
        )
        current_secret_payload = current_secrets if current_secrets_exists else None
        current_hashes = (_payload_sha(current_env), _payload_sha(current_secret_payload))
        old_hashes = (journal["old_env_sha256"], journal["old_secrets_sha256"])
        new_hashes = (journal["new_env_sha256"], journal["new_secrets_sha256"])
        env_stage = env_path.parent / f".{env_path.name}.pitr-{transaction_dir.name}"
        secrets_stage = secrets_path.parent / f".{secrets_path.name}.pitr-{transaction_dir.name}"
        if current_hashes == new_hashes:
            validate_environment(current_env)
            expected_receipt = _completion_receipt_record(
                receipt_context,
                transaction_id=transaction_dir.name,
                new_env_sha256=journal["new_env_sha256"],
                new_secrets_sha256=journal["new_secrets_sha256"],
            )
            if receipt is not None and receipt != expected_receipt:
                raise RuntimeError(
                    "PITR completion receipt conflicts with unfinished transaction"
                )
            _write_completion_receipt(receipt_context, expected_receipt)
        elif all(
            current in {old, new}
            for current, old, new in zip(current_hashes, old_hashes, new_hashes)
        ):
            if receipt is not None or journal["state"] == "committed":
                journal["state"] = "fenced"
                journal["error"] = "committed generation drifted from its receipt"
                _write_journal(transaction_dir, journal, uid=uid, gid=gid)
                raise RuntimeError("completed PITR transaction target files drifted")
            journal["state"] = "recovering"
            journal["error"] = ""
            _write_journal(transaction_dir, journal, uid=uid, gid=gid)
            _restore_target(env_path, original_env, uid=uid, gid=gid)
            _restore_target(secrets_path, original_secrets, uid=uid, gid=gid)
            restored_secret = (
                read_controlled_file(
                    secrets_path,
                    label="restored PITR secrets",
                    required=True,
                    expected_uid=uid,
                    exact_mode=0o600,
                )
                if original_secrets is not None
                else None
            )
            restored_env = read_controlled_file(
                env_path,
                label="restored project env",
                required=True,
                expected_uid=uid,
                exact_mode=0o600,
            )
            if (_payload_sha(restored_env), _payload_sha(restored_secret)) != old_hashes:
                raise RuntimeError("PITR transaction crash rollback postcondition failed")
        else:
            journal["state"] = "fenced"
            journal["error"] = "target digest is outside the recorded generations"
            _write_journal(transaction_dir, journal, uid=uid, gid=gid)
            raise RuntimeError("unfinished PITR transaction has ambiguous target generations")
        env_stage.unlink(missing_ok=True)
        secrets_stage.unlink(missing_ok=True)
        shutil.rmtree(transaction_dir)
        _fsync_directory(transaction_root)


def commit_split_transaction(
    *,
    env_path: Path,
    secrets_path: Path,
    transaction_root: Path,
    transaction_id: str,
    old_env: bytes,
    old_secrets: bytes | None,
    new_env: bytes,
    new_secrets: bytes,
    uid: int,
    gid: int,
    read_controlled_file: ReadControlledFile,
    validate_environment: ValidateEnvironment,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise RuntimeError("PITR transaction ID is invalid")
    receipt_context = ReceiptContext(
        transaction_root, env_path, secrets_path, uid, gid, read_controlled_file
    )
    completion_receipt = _completion_receipt_record(
        receipt_context,
        transaction_id=transaction_id,
        new_env_sha256=_payload_sha(new_env),
        new_secrets_sha256=_payload_sha(new_secrets),
    )
    existing_receipt = _read_completion_receipt(receipt_context, transaction_id)
    if existing_receipt is not None:
        if existing_receipt != completion_receipt:
            raise RuntimeError(
                "PITR completion receipt conflicts with the requested payload"
            )
        actual_env = read_controlled_file(
            env_path,
            label="completed PITR project env",
            required=True,
            expected_uid=uid,
            exact_mode=0o600,
        )
        actual_secrets = read_controlled_file(
            secrets_path,
            label="completed PITR secrets",
            required=True,
            expected_uid=uid,
            exact_mode=0o600,
        )
        if actual_env != new_env or actual_secrets != new_secrets:
            raise RuntimeError("completed PITR transaction target files drifted")
        validate_environment(actual_env)
        return
    transaction_dir = _prepare_transaction_dir(
        transaction_root,
        transaction_id,
        expected_uid=uid,
        expected_gid=gid,
    )
    journal = {
        "transaction_id": transaction_id,
        "env_path": str(env_path),
        "secrets_path": str(secrets_path),
        "state": "initializing",
        "old_env_sha256": _payload_sha(old_env),
        "old_secrets_sha256": _payload_sha(old_secrets),
        "old_secrets_present": old_secrets is not None,
        "new_env_sha256": _payload_sha(new_env),
        "new_secrets_sha256": _payload_sha(new_secrets),
        "error": "",
    }
    _write_journal(transaction_dir, journal, uid=uid, gid=gid)
    _write_new_controlled(
        transaction_dir / "original-project.env", old_env, uid=uid, gid=gid
    )
    if old_secrets is not None:
        _write_new_controlled(
            transaction_dir / "original-secrets.env", old_secrets, uid=uid, gid=gid
        )
    journal["state"] = "prepared"
    _write_journal(transaction_dir, journal, uid=uid, gid=gid)
    _fsync_directory(transaction_dir)

    env_stage = _write_staged(
        env_path, new_env, uid=uid, gid=gid, suffix=transaction_id
    )
    secrets_stage = _write_staged(
        secrets_path, new_secrets, uid=uid, gid=gid, suffix=transaction_id
    )
    committed_secrets = False
    committed_env = False
    try:
        journal["state"] = "commit-secrets"
        _write_journal(transaction_dir, journal, uid=uid, gid=gid)
        os.replace(secrets_stage, secrets_path)
        committed_secrets = True
        _fsync_directory(secrets_path.parent)
        journal["state"] = "secrets-committed"
        _write_journal(transaction_dir, journal, uid=uid, gid=gid)
        journal["state"] = "commit-env"
        _write_journal(transaction_dir, journal, uid=uid, gid=gid)
        os.replace(env_stage, env_path)
        committed_env = True
        _fsync_directory(env_path.parent)
        journal["state"] = "env-committed"
        _write_journal(transaction_dir, journal, uid=uid, gid=gid)
        actual_secrets = read_controlled_file(
            secrets_path,
            label="committed PITR secrets",
            required=True,
            expected_uid=uid,
            exact_mode=0o600,
        )
        actual_env = read_controlled_file(
            env_path,
            label="committed project env",
            required=True,
            expected_uid=uid,
            exact_mode=0o600,
        )
        if actual_secrets != new_secrets or actual_env != new_env:
            raise RuntimeError("PITR split transaction postcondition failed")
        validate_environment(actual_env)
        journal["state"] = "committed"
        _write_journal(transaction_dir, journal, uid=uid, gid=gid)
    except BaseException as exc:
        rollback_errors: list[str] = []
        try:
            if committed_env:
                _restore_target(env_path, old_env, uid=uid, gid=gid)
            else:
                env_stage.unlink(missing_ok=True)
        except BaseException as rollback_exc:
            rollback_errors.append(f"project env: {rollback_exc}")
        try:
            if committed_secrets:
                _restore_target(secrets_path, old_secrets, uid=uid, gid=gid)
            else:
                secrets_stage.unlink(missing_ok=True)
        except BaseException as rollback_exc:
            rollback_errors.append(f"secrets: {rollback_exc}")
        journal["state"] = "rollback-failed" if rollback_errors else "rolled-back"
        journal["error"] = "; ".join(rollback_errors) or str(exc)
        _write_journal(transaction_dir, journal, uid=uid, gid=gid)
        if rollback_errors:
            raise RuntimeError(
                f"PITR split transaction failed ({exc}); rollback also failed: "
                + "; ".join(rollback_errors)
            ) from exc
        shutil.rmtree(transaction_dir)
        _fsync_directory(transaction_root)
        raise
    else:
        _write_completion_receipt(receipt_context, completion_receipt)
        env_stage.unlink(missing_ok=True)
        secrets_stage.unlink(missing_ok=True)
        shutil.rmtree(transaction_dir)
        _fsync_directory(transaction_root)
