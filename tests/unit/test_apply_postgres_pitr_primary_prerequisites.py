import hashlib
import os
from pathlib import Path

import pytest

from scripts.ha import apply_postgres_pitr_primary_prerequisites as module
from scripts.ha.pitr_cluster_topology import ClusterTopology


TXID = "0123456789abcdef0123456789abcdef"


def _env(**overrides):
    values = {
        "POSTGRES_PITR_CLUSTER": "mvn-api",
        "POSTGRES_PITR_S3_BUCKET": "mvn-postgres-pitr",
        "POSTGRES_PITR_S3_ENDPOINT_URL": (
            "https://reviewed.r2.cloudflarestorage.com"
        ),
        "POSTGRES_PITR_S3_REGION": "auto",
        "POSTGRES_PITR_S3_ACCESS_KEY_ID": "access-key-id",
        "POSTGRES_PITR_S3_SECRET_ACCESS_KEY": "super-secret-key",
        "POSTGRES_PITR_S3_KEY_PREFIX": "postgres/pitr",
    }
    values.update(overrides)
    return values


def _destination_fingerprint(values):
    payload = "\n".join(
        values[name]
        for name in (
            "POSTGRES_PITR_S3_BUCKET",
            "POSTGRES_PITR_S3_ENDPOINT_URL",
            "POSTGRES_PITR_S3_REGION",
            "POSTGRES_PITR_S3_KEY_PREFIX",
        )
    ) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


@pytest.fixture
def reviewed_destination(monkeypatch):
    values = _env()
    monkeypatch.setattr(
        module,
        "EXPECTED_DESTINATION_FINGERPRINT",
        _destination_fingerprint(values),
    )
    return values


def test_collect_and_render_env_redacts_only_credentials(reviewed_destination):
    config = module.collect_inputs(environ=reviewed_destination, no_prompt=True)

    rendered = module.render_env(config, redact=True)

    assert "POSTGRES_PITR_CLUSTER=mvn-api" in rendered
    assert "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr" in rendered
    assert "access-key-id" not in rendered
    assert "super-secret-key" not in rendered
    assert "POSTGRES_PITR_S3_ACCESS_KEY_ID=redacted" in rendered
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=redacted" in rendered


def test_input_requires_exact_reviewed_destination_and_logical_namespace(
    reviewed_destination,
):
    wrong_destination = dict(reviewed_destination)
    wrong_destination["POSTGRES_PITR_S3_BUCKET"] = "other-private-bucket"
    with pytest.raises(RuntimeError, match="reviewed production archive"):
        module.collect_inputs(environ=wrong_destination, no_prompt=True)

    wrong_cluster = dict(reviewed_destination)
    wrong_cluster["POSTGRES_PITR_CLUSTER"] = "zakup"
    with pytest.raises(RuntimeError, match="logical namespace"):
        module.collect_inputs(environ=wrong_cluster, no_prompt=True)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("POSTGRES_PITR_S3_ENDPOINT_URL", "https://cdn.mvn.by", "cloudflarestorage"),
        ("POSTGRES_PITR_S3_ACCESS_KEY_ID", "has space", "whitespace"),
        ("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", "line\nbreak", "single-line"),
        ("POSTGRES_PITR_S3_BUCKET", "", "missing required"),
    ],
)
def test_input_rejects_unsafe_or_missing_values(
    reviewed_destination, name, value, message
):
    candidate = dict(reviewed_destination)
    candidate[name] = value
    with pytest.raises(RuntimeError, match=message):
        module.collect_inputs(environ=candidate, no_prompt=True)


def test_env_file_returns_only_pitr_keys_without_mutating_ambient_env(
    tmp_path, monkeypatch
):
    path = tmp_path / "pitr.env"
    path.write_text(
        "\n".join(
            [
                "POSTGRES_PITR_CLUSTER=mvn-api",
                "POSTGRES_PITR_S3_BUCKET='mvn-postgres-pitr'",
                "GH_TOKEN=must-not-load",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    monkeypatch.delenv("POSTGRES_PITR_CLUSTER", raising=False)

    loaded = module.load_env_file(path)

    assert loaded == {
        "POSTGRES_PITR_CLUSTER": "mvn-api",
        "POSTGRES_PITR_S3_BUCKET": "mvn-postgres-pitr",
    }
    assert "POSTGRES_PITR_CLUSTER" not in os.environ
    assert "GH_TOKEN" not in loaded


def test_env_file_rejects_duplicates_symlinks_broad_mode_and_wrong_owner(
    tmp_path, monkeypatch
):
    duplicated = tmp_path / "duplicated.env"
    duplicated.write_text(
        "POSTGRES_PITR_CLUSTER=mvn-api\nPOSTGRES_PITR_CLUSTER=mvn-api\n",
        encoding="utf-8",
    )
    duplicated.chmod(0o600)
    with pytest.raises(RuntimeError, match="duplicate key"):
        module.load_env_file(duplicated)

    broad = tmp_path / "broad.env"
    broad.write_text("POSTGRES_PITR_CLUSTER=mvn-api\n", encoding="utf-8")
    broad.chmod(0o644)
    with pytest.raises(RuntimeError, match="group or other"):
        module.load_env_file(broad)

    secure = tmp_path / "secure.env"
    secure.write_text("POSTGRES_PITR_CLUSTER=mvn-api\n", encoding="utf-8")
    secure.chmod(0o600)
    linked = tmp_path / "linked.env"
    linked.symlink_to(secure)
    with pytest.raises(RuntimeError, match="non-symlink"):
        module.load_env_file(linked)

    monkeypatch.setattr(module.os, "geteuid", lambda: secure.stat().st_uid + 1)
    with pytest.raises(RuntimeError, match="current user"):
        module.load_env_file(secure)


def test_identity_file_is_absolute_owner_only_regular_and_single_link(tmp_path):
    identity = tmp_path / "identity"
    identity.write_text("private-key", encoding="utf-8")
    identity.chmod(0o600)
    assert module.validate_identity_file(str(identity)) == identity

    identity.chmod(0o640)
    with pytest.raises(RuntimeError, match="group or other"):
        module.validate_identity_file(str(identity))

    identity.chmod(0o600)
    linked = tmp_path / "linked"
    linked.symlink_to(identity)
    with pytest.raises(RuntimeError, match="non-symlink"):
        module.validate_identity_file(str(linked))

    hardlink = tmp_path / "hardlink"
    os.link(identity, hardlink)
    with pytest.raises(RuntimeError, match="exactly one"):
        module.validate_identity_file(str(identity))


@pytest.mark.parametrize(
    "unsafe_option",
    ["--ssh-host", "--project-dir", "--compose-file", "--bootstrap-helper"],
)
def test_unreviewed_remote_overrides_are_not_cli_options(unsafe_option):
    with pytest.raises(SystemExit):
        module.parse_args([unsafe_option, "203.0.113.5"])


@pytest.mark.parametrize(
    "legacy_phase",
    [
        "preflight",
        "provision-node",
        "configure-node",
        "scrub-node",
        "enable-timers",
        "basebackup",
    ],
)
def test_unsafe_standalone_mutation_phases_are_not_public_cli(legacy_phase):
    with pytest.raises(SystemExit):
        module.parse_args(["--phase", legacy_phase])


def test_dry_run_requires_txid_and_never_prints_secrets(
    reviewed_destination, monkeypatch, capsys
):
    for name, value in reviewed_destination.items():
        monkeypatch.setenv(name, value)

    assert module.main(["--dry-run", "--no-prompt"]) == 1
    assert module.main(
        ["--dry-run", "--no-prompt", "--transaction-id", TXID]
    ) == 0
    output = capsys.readouterr().out
    assert "super-secret-key" not in output
    assert "access-key-id" not in output
    assert "redacted" in output


def test_probe_only_needs_no_secrets_or_transaction_id(tmp_path, monkeypatch):
    identity = tmp_path / "identity"
    identity.write_text("private-key", encoding="utf-8")
    identity.chmod(0o600)
    topology = ClusterTopology(
        primary=module.PATRONI_NODES[0],
        standby=module.PATRONI_NODES[1],
        system_identifier="7423456789012345678",
        timeline=9,
    )
    monkeypatch.setattr(module, "create_context", lambda *_args: object())
    monkeypatch.setattr(module, "validate_effective_config", lambda *_args: None)
    monkeypatch.setattr(
        module, "discover_cluster_topology", lambda **_kwargs: topology
    )
    monkeypatch.setattr(
        module,
        "collect_inputs",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("read secrets")),
    )

    assert module.main(
        ["--probe-only", "--identity-file", str(identity)]
    ) == 0


def test_maintenance_rejects_env_file_before_any_connection(tmp_path, capsys):
    env_file = tmp_path / "pitr.env"
    env_file.write_text("POSTGRES_PITR_CLUSTER=mvn-api\n", encoding="utf-8")
    env_file.chmod(0o600)

    assert module.main(
        [
            "--phase",
            "verify",
            "--transaction-id",
            TXID,
            "--env-file",
            str(env_file),
        ]
    ) == 1
    assert "--env-file is not accepted" in capsys.readouterr().out
