from scripts.ha import apply_postgres_pitr_primary_prerequisites as controller
from scripts.ha.pitr_cluster_migration import MigrationResult
from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES, PinnedSshContext


TXID = "0123456789abcdef0123456789abcdef"


def _context(tmp_path):
    return PinnedSshContext(
        identity_file=tmp_path / "identity",
        known_hosts_file=tmp_path / "known-hosts",
        config_file=tmp_path / "config",
    )


def _topology():
    by_alias = {node.alias: node for node in PATRONI_NODES}
    return ClusterTopology(
        primary=by_alias["mvn-api"],
        standby=by_alias["zakup"],
        system_identifier="7423456789012345678",
        timeline=9,
    )


def _controller_input():
    return controller.PitrInput(
        cluster="mvn-api",
        bucket="mvn-postgres-pitr",
        endpoint_url="https://reviewed.r2.cloudflarestorage.com",
        region="auto",
        access_key_id="access",
        secret_access_key="secret",
        key_prefix="postgres/pitr",
    )


def _patch_controller_connection(monkeypatch, tmp_path):
    context = _context(tmp_path)
    monkeypatch.setattr(controller, "validate_identity_file", lambda _path: tmp_path / "id")
    monkeypatch.setattr(controller, "create_context", lambda *_args: context)
    monkeypatch.setattr(controller, "validate_effective_config", lambda *_args: None)
    return context


def test_controller_migrate_cluster_entrypoint_passes_one_env_and_root_txid(
    tmp_path, monkeypatch
):
    context = _patch_controller_connection(monkeypatch, tmp_path)
    captured = []
    monkeypatch.setattr(
        controller,
        "collect_inputs",
        lambda **_kwargs: _controller_input(),
    )

    def fake_migrate(**kwargs):
        captured.append(kwargs)
        return MigrationResult(
            transaction_id=TXID,
            primary_alias="mvn-api",
            standby_alias="zakup",
            system_identifier="7423456789012345678",
            timeline=9,
        )

    monkeypatch.setattr(controller, "migrate_cluster", fake_migrate)

    assert controller.main(
        [
            "--phase",
            "migrate-cluster",
            "--transaction-id",
            TXID,
            "--identity-file",
            str(tmp_path / "id"),
            "--no-prompt",
        ]
    ) == 0
    assert len(captured) == 1
    assert captured[0]["context"] == context
    assert captured[0]["transaction_id"] == TXID
    assert captured[0]["env_text"] == controller.render_env(_controller_input())


def test_controller_standalone_phase_requires_and_propagates_root_txid(
    tmp_path, monkeypatch
):
    context = _patch_controller_connection(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(controller, "discover_cluster_topology", lambda **_kwargs: _topology())
    monkeypatch.setattr(
        controller,
        "run_remote_maintenance_phase",
        lambda **kwargs: calls.append(kwargs),
    )

    assert controller.main(
        [
            "--phase",
            "verify",
            "--transaction-id",
            TXID,
            "--identity-file",
            str(tmp_path / "id"),
            "--no-prompt",
        ]
    ) == 0
    assert len(calls) == 1
    assert calls[0]["context"] == context
    assert calls[0]["transaction_id"] == TXID
    assert calls[0]["phase"] == "verify"


def test_controller_probe_only_is_the_only_live_mode_without_transaction_id(
    tmp_path, monkeypatch
):
    _patch_controller_connection(monkeypatch, tmp_path)
    monkeypatch.setattr(controller, "discover_cluster_topology", lambda **_kwargs: _topology())

    assert controller.main(
        ["--probe-only", "--identity-file", str(tmp_path / "id")]
    ) == 0
    assert controller.main(
        ["--phase", "verify", "--identity-file", str(tmp_path / "id")]
    ) == 1
