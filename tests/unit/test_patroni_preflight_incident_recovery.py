import hashlib
import json
from pathlib import Path

import pytest

from scripts.ha import patroni_preflight_incident_recovery as recovery


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _journal(*, operation="idle", completed=None, node="mvn-api"):
    return {
        "baseline_primary": "mvn-api",
        "baseline_system_identifier": "7423456789012345678",
        "baseline_timeline": 9,
        "completed": completed or ["record:baseline-primary-mvn-api"],
        "controller_sha256": recovery.EXPECTED_CONTROLLER_SHA256,
        "current_image": "ghcr.io/mvnby/air-api/patroni@sha256:" + "1" * 64,
        "node": node,
        "operation": operation,
        "target_image": "ghcr.io/mvnby/air-api/patroni@sha256:" + "2" * 64,
        "transaction_id": "a" * 32,
        "version": 1,
    }


def _contract(journal, *, before_operation="idle"):
    before = _canonical(journal)
    terminal = dict(journal)
    terminal["operation"] = "idle"
    terminal["completed"] = ["record:baseline-primary-mvn-api", "abort"]
    after = _canonical(terminal)
    return recovery.IncidentJournalContract(
        node=journal["node"],
        before_sha256=hashlib.sha256(before).hexdigest(),
        after_sha256=hashlib.sha256(after).hexdigest(),
        before_operation=before_operation,
    )


def _receipt(contract):
    return recovery.receipt_document(
        contract,
        transaction_id="a" * 32,
        maintenance_transaction_id="b" * 32,
        recovery_deploy_sha="c" * 40,
        current_image="ghcr.io/mvnby/air-api/patroni@sha256:" + "1" * 64,
        corrected_compose_contract_sha256="d" * 64,
        compose_source_sha256="e" * 64,
        incident_controller_sha256=recovery.EXPECTED_CONTROLLER_SHA256,
    )


@pytest.mark.parametrize("operation", ["idle", "abort"])
def test_exact_before_transforms_only_operation_and_completed(operation):
    journal = _journal(operation=operation)
    contract = _contract(journal, before_operation=operation)
    state = recovery.validate_journal(_canonical(journal), contract)

    transformed = recovery.terminal_journal(state.journal, contract)

    changed = {
        key for key in journal | transformed if journal.get(key) != transformed.get(key)
    }
    assert changed == {"operation", "completed"} if operation == "abort" else {"completed"}
    assert transformed["operation"] == "idle"
    assert transformed["completed"] == [
        "record:baseline-primary-mvn-api",
        "abort",
    ]
    assert recovery.validate_journal(_canonical(transformed), contract).state == "after"


def test_after_state_is_idempotent_and_exact():
    before = _journal()
    contract = _contract(before)
    after = recovery.terminal_journal(before, contract)

    state = recovery.validate_journal(_canonical(after), contract)

    assert state.state == "after"
    assert recovery.validate_journal(state.raw, contract) == state


@pytest.mark.parametrize(
    "completed",
    [
        ["record:baseline-primary-mvn-api", "update-node"],
        ["record:baseline-primary-mvn-api", "record:standby-updated"],
        ["record:baseline-primary-mvn-api", "apply-archive-command"],
    ],
)
def test_rejects_any_completed_mutation_record(completed):
    journal = _journal(completed=completed)
    raw = _canonical(journal)
    contract = recovery.IncidentJournalContract(
        node="mvn-api",
        before_sha256=hashlib.sha256(raw).hexdigest(),
        after_sha256="f" * 64,
        before_operation="idle",
    )

    with pytest.raises(RuntimeError, match="database or DCS mutation"):
        recovery.validate_journal(raw, contract)


@pytest.mark.parametrize(
    "field",
    ["dcs_baseline", "dcs_baseline_sha256", "legacy_archive_command"],
)
def test_rejects_dcs_evidence_even_with_matching_before_digest(field):
    journal = _journal()
    journal[field] = {} if field == "dcs_baseline" else "x"
    raw = _canonical(journal)
    contract = recovery.IncidentJournalContract(
        node="mvn-api",
        before_sha256=hashlib.sha256(raw).hexdigest(),
        after_sha256="f" * 64,
        before_operation="idle",
    )

    with pytest.raises(RuntimeError, match="DCS mutation evidence"):
        recovery.validate_journal(raw, contract)


def test_rejects_noncanonical_or_unattested_bytes():
    journal = _journal()
    raw = _canonical(journal)
    contract = _contract(journal)

    with pytest.raises(RuntimeError, match="outside the exact contract"):
        recovery.validate_journal(raw + b"\n", contract)

    noncanonical = json.dumps(journal, indent=2).encode() + b"\n"
    forged = recovery.IncidentJournalContract(
        node="mvn-api",
        before_sha256=hashlib.sha256(noncanonical).hexdigest(),
        after_sha256=contract.after_sha256,
        before_operation="idle",
    )
    with pytest.raises(RuntimeError, match="not exact canonical"):
        recovery.validate_journal(noncanonical, forged)


def test_receipt_is_canonical_and_root_helper_is_idempotent(tmp_path, monkeypatch):
    contract = _contract(_journal())
    receipt = _receipt(contract)
    expected = recovery.canonical_json(receipt)
    writes = []

    monkeypatch.setattr(recovery.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        recovery,
        "_root_regular",
        lambda path, **_kwargs: (_ for _ in ()).throw(FileNotFoundError())
        if not writes
        else writes[-1],
    )
    monkeypatch.setattr(recovery, "_atomic_root_file", lambda path, raw: writes.append(raw))

    assert recovery.ensure_root_receipt(Path(tmp_path / "receipt.json"), receipt) == expected
    assert recovery.ensure_root_receipt(Path(tmp_path / "receipt.json"), receipt) == expected
    assert writes == [expected]


def test_receipt_rejects_drift_and_non_root(tmp_path, monkeypatch):
    contract = _contract(_journal())
    receipt = _receipt(contract)
    monkeypatch.setattr(recovery.os, "geteuid", lambda: 1000)
    with pytest.raises(RuntimeError, match="requires root"):
        recovery.ensure_root_receipt(tmp_path / "receipt.json", receipt)

    monkeypatch.setattr(recovery.os, "geteuid", lambda: 0)
    monkeypatch.setattr(recovery, "_root_regular", lambda *_args, **_kwargs: b"{}\n")
    with pytest.raises(RuntimeError, match="differs from the exact contract"):
        recovery.ensure_root_receipt(tmp_path / "receipt.json", receipt)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"recovery_deploy_sha": "c" * 39}, "recovery deploy SHA"),
        ({"current_image": "patroni:latest"}, "immutable reviewed digest"),
        (
            {"corrected_compose_contract_sha256": "d" * 63},
            "corrected Compose contract SHA-256",
        ),
        ({"compose_source_sha256": "e" * 63}, "Compose source SHA-256"),
        ({"incident_controller_sha256": "f" * 64}, "fenced generation"),
    ],
)
def test_receipt_requires_exact_durable_evidence(overrides, message):
    contract = _contract(_journal())
    values = {
        "transaction_id": "a" * 32,
        "maintenance_transaction_id": "b" * 32,
        "recovery_deploy_sha": "c" * 40,
        "current_image": "ghcr.io/mvnby/air-api/patroni@sha256:" + "1" * 64,
        "corrected_compose_contract_sha256": "d" * 64,
        "compose_source_sha256": "e" * 64,
        "incident_controller_sha256": recovery.EXPECTED_CONTROLLER_SHA256,
    }
    values.update(overrides)

    with pytest.raises(RuntimeError, match=message):
        recovery.receipt_document(contract, **values)


def test_receipt_contains_all_reviewed_evidence():
    receipt = _receipt(_contract(_journal()))

    assert receipt["recovery_deploy_sha"] == "c" * 40
    assert receipt["current_image"].endswith("1" * 64)
    assert receipt["corrected_compose_contract_sha256"] == "d" * 64
    assert receipt["compose_source_sha256"] == "e" * 64
    assert receipt["incident_controller_sha256"] == recovery.EXPECTED_CONTROLLER_SHA256


def test_module_contains_no_runtime_mutation_commands():
    source = Path(recovery.__file__).read_text(encoding="utf-8")
    forbidden = (
        "docker compose up",
        "docker pull",
        "set_env_image",
        "pg_switch_wal",
        "subprocess.run",
        "import subprocess",
    )
    assert not any(command in source for command in forbidden)
