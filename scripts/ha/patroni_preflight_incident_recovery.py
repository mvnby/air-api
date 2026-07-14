#!/usr/bin/env python3
"""Fail-closed journal terminalization for the fenced preflight incident.

This module intentionally has no SSH, Docker, Patroni, or DCS operations.  Its
only mutation is an atomic, byte-attested transition of an already validated
rollout journal, plus creation/validation of a durable root-only receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DIGEST_RE = re.compile(r"[0-9a-f]{64}")
TRANSACTION_RE = re.compile(r"[0-9a-f]{32}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
IMAGE_RE = re.compile(
    r"ghcr[.]io/mvnby/air-api/patroni@sha256:[0-9a-f]{64}"
)
EXPECTED_CONTROLLER_SHA256 = (
    "35eb1591dc27de42e9ac72887801818850bd358fe2cbd1f56273f77a484f4d17"
)
FORBIDDEN_DCS_FIELDS = {
    "dcs_baseline",
    "dcs_baseline_sha256",
    "legacy_archive_command",
}
MUTATING_COMPLETIONS = {
    "apply-archive-command",
    "finalize",
    "prove-archive",
    "revert-archive-command",
    "rollback-node",
    "switchover",
    "update-node",
    "record:standby-updated",
    "record:switched-over",
    "record:former-primary-updated",
    "record:archive-command-applied",
    "record:archive-proved",
    "record:final-proved",
    "record:archive-command-reverted",
}


@dataclass(frozen=True)
class IncidentJournalContract:
    node: str
    before_sha256: str
    after_sha256: str
    before_operation: str
    baseline_primary: str = "mvn-api"

    def __post_init__(self) -> None:
        if self.node not in {"mvn-api", "zakup"}:
            raise ValueError("incident journal node is not reviewed")
        if not DIGEST_RE.fullmatch(self.before_sha256):
            raise ValueError("before journal SHA-256 is invalid")
        if not DIGEST_RE.fullmatch(self.after_sha256):
            raise ValueError("after journal SHA-256 is invalid")
        if self.before_sha256 == self.after_sha256:
            raise ValueError("before and after journal SHA-256 must differ")
        if self.before_operation not in {"idle", "abort"}:
            raise ValueError("incident journal operation must be idle or abort")
        if self.baseline_primary not in {"mvn-api", "zakup"}:
            raise ValueError("incident baseline primary is not reviewed")

    @property
    def baseline_record(self) -> str:
        return "record:baseline-primary-" + self.baseline_primary


INCIDENT_CONTRACTS = {
    "mvn-api": IncidentJournalContract(
        node="mvn-api",
        before_sha256=(
            "e34fa16900de4051f0dd3087b9c2cfd7ee1bd96cfa59126036fba2c1c6022be6"
        ),
        after_sha256=(
            "700d106e6b7f0cc6b32ddc937d06adcd87c34698d2c32750ac0e83672c42ff52"
        ),
        before_operation="idle",
    ),
    "zakup": IncidentJournalContract(
        node="zakup",
        before_sha256=(
            "9ab65567b9e84a5122707ebf8becd532d7a766405fe54a0d3398a4233727b518"
        ),
        after_sha256=(
            "5fd134bd3a9c6a951e3e6a9cf82b66ae2b379a9282c073e0253398601414d482"
        ),
        before_operation="abort",
    ),
}


@dataclass(frozen=True)
class JournalState:
    state: str
    raw: bytes
    journal: dict[str, object]


def canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_canonical(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("incident journal is not valid JSON") from exc
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise RuntimeError("incident journal is not exact canonical JSON")
    return value


def _validate_common(
    journal: Mapping[str, object], contract: IncidentJournalContract
) -> None:
    if journal.get("version") != 1:
        raise RuntimeError("incident journal version is not reviewed")
    if journal.get("node") != contract.node:
        raise RuntimeError("incident journal node differs from the contract")
    if journal.get("baseline_primary") != contract.baseline_primary:
        raise RuntimeError("incident journal baseline primary drifted")
    if journal.get("controller_sha256") != EXPECTED_CONTROLLER_SHA256:
        raise RuntimeError("incident journal controller generation drifted")
    if FORBIDDEN_DCS_FIELDS.intersection(journal):
        raise RuntimeError("incident journal contains DCS mutation evidence")
    completed = journal.get("completed")
    if not isinstance(completed, list) or any(
        not isinstance(item, str) for item in completed
    ):
        raise RuntimeError("incident journal completed list is invalid")
    if len(completed) != len(set(completed)):
        raise RuntimeError("incident journal completed list has duplicates")
    if MUTATING_COMPLETIONS.intersection(completed):
        raise RuntimeError("incident journal records a database or DCS mutation")
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str) or not TRANSACTION_RE.fullmatch(
        transaction_id
    ):
        raise RuntimeError("incident journal transaction ID is invalid")


def terminal_journal(
    journal: Mapping[str, object], contract: IncidentJournalContract
) -> dict[str, object]:
    _validate_common(journal, contract)
    if journal.get("operation") != contract.before_operation:
        raise RuntimeError("incident journal before operation drifted")
    if journal.get("completed") != [contract.baseline_record]:
        raise RuntimeError("incident journal crossed the preflight-only boundary")
    transformed = dict(journal)
    transformed["operation"] = "idle"
    transformed["completed"] = [contract.baseline_record, "abort"]
    return transformed


def validate_journal(
    raw: bytes, contract: IncidentJournalContract
) -> JournalState:
    digest = sha256_bytes(raw)
    if digest not in {contract.before_sha256, contract.after_sha256}:
        raise RuntimeError("incident journal SHA-256 is outside the exact contract")
    journal = _parse_canonical(raw)
    _validate_common(journal, contract)
    if digest == contract.before_sha256:
        transformed = terminal_journal(journal, contract)
        if sha256_bytes(canonical_json(transformed)) != contract.after_sha256:
            raise RuntimeError("reviewed terminal journal SHA-256 is inconsistent")
        return JournalState(state="before", raw=raw, journal=journal)
    if journal.get("operation") != "idle" or journal.get("completed") != [
        contract.baseline_record,
        "abort",
    ]:
        raise RuntimeError("terminal incident journal shape drifted")
    return JournalState(state="after", raw=raw, journal=journal)


def _root_regular(path: Path, *, mode: int, maximum: int = 1_048_576) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_size > maximum
    ):
        raise RuntimeError(f"unsafe root-only file: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"root-only file changed while opening: {path}")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum or os.read(descriptor, 1):
            raise RuntimeError(f"root-only file exceeds its limit: {path}")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise RuntimeError(f"root-only file changed while reading: {path}")
        return raw
    finally:
        os.close(descriptor)


def _root_directory(path: Path) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError(f"unsafe root-only directory: {path}")


def _atomic_root_file(path: Path, raw: bytes) -> None:
    _root_directory(path.parent)
    staged = path.parent / (".stage-" + secrets.token_hex(16))
    descriptor = os.open(
        staged,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, 0, 0)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RuntimeError("short incident recovery write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(staged, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass


def terminalize_journal(
    path: Path, contract: IncidentJournalContract
) -> JournalState:
    if os.geteuid() != 0:
        raise RuntimeError("incident recovery requires root")
    state = validate_journal(_root_regular(path, mode=0o600), contract)
    if state.state == "after":
        return state
    transformed = terminal_journal(state.journal, contract)
    _atomic_root_file(path, canonical_json(transformed))
    terminal = validate_journal(_root_regular(path, mode=0o600), contract)
    if terminal.state != "after":
        raise RuntimeError("incident journal did not reach its terminal generation")
    return terminal


def receipt_document(
    contract: IncidentJournalContract,
    *,
    transaction_id: str,
    maintenance_transaction_id: str,
    recovery_deploy_sha: str,
    current_image: str,
    corrected_compose_contract_sha256: str,
    compose_source_sha256: str,
    incident_controller_sha256: str,
) -> dict[str, object]:
    for label, value in (
        ("transaction", transaction_id),
        ("maintenance transaction", maintenance_transaction_id),
    ):
        if not TRANSACTION_RE.fullmatch(value):
            raise RuntimeError(f"{label} ID is invalid")
    if not COMMIT_RE.fullmatch(recovery_deploy_sha):
        raise RuntimeError("recovery deploy SHA is invalid")
    if not IMAGE_RE.fullmatch(current_image):
        raise RuntimeError("current Patroni image is not an immutable reviewed digest")
    for label, value in (
        ("corrected Compose contract", corrected_compose_contract_sha256),
        ("Compose source", compose_source_sha256),
        ("incident controller", incident_controller_sha256),
    ):
        if not DIGEST_RE.fullmatch(value):
            raise RuntimeError(f"{label} SHA-256 is invalid")
    if incident_controller_sha256 != EXPECTED_CONTROLLER_SHA256:
        raise RuntimeError("incident controller SHA-256 differs from the fenced generation")
    return {
        "after_journal_sha256": contract.after_sha256,
        "before_journal_sha256": contract.before_sha256,
        "compose_source_sha256": compose_source_sha256,
        "corrected_compose_contract_sha256": corrected_compose_contract_sha256,
        "current_image": current_image,
        "incident_controller_sha256": incident_controller_sha256,
        "kind": "patroni-preflight-incident-recovery",
        "maintenance_transaction_id": maintenance_transaction_id,
        "node": contract.node,
        "recovery_deploy_sha": recovery_deploy_sha,
        "transaction_id": transaction_id,
        "version": 1,
    }


def ensure_root_receipt(path: Path, receipt: Mapping[str, object]) -> bytes:
    if os.geteuid() != 0:
        raise RuntimeError("incident recovery receipt requires root")
    expected = canonical_json(receipt)
    try:
        actual = _root_regular(path, mode=0o600, maximum=16_384)
    except FileNotFoundError:
        _atomic_root_file(path, expected)
        actual = _root_regular(path, mode=0o600, maximum=16_384)
    if actual != expected:
        raise RuntimeError("incident recovery receipt differs from the exact contract")
    return actual
