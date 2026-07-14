import ast
import pytest

from scripts.ha import apply_postgres_pitr_primary_prerequisites as module
from scripts.ha import pitr_remote_executors
from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ha.pitr_pinned_ssh import effective_config, ssh_args


TXID = "0123456789abcdef0123456789abcdef"


def _context(tmp_path):
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)
    return module.create_context(tmp_path, identity)


def _topology(*, primary=0, timeline=9, system_identifier="7423456789012345678"):
    standby = 1 - primary
    return ClusterTopology(
        primary=module.PATRONI_NODES[primary],
        standby=module.PATRONI_NODES[standby],
        system_identifier=system_identifier,
        timeline=timeline,
    )


def test_generated_config_resolves_alias_to_one_effective_identity(tmp_path):
    context = _context(tmp_path)
    node = module.PATRONI_NODES[0]
    effective = effective_config(node, context)

    assert effective["hostname"] == [node.physical_host]
    assert effective["user"] == [node.user]
    assert effective["hostkeyalias"] == [node.alias]
    assert effective["identityfile"] == [str(context.identity_file)]
    assert effective["identitiesonly"] == ["yes"]
    assert effective["stricthostkeychecking"] == ["true"]
    assert effective["userknownhostsfile"] == [str(context.known_hosts_file)]
    assert ssh_args(node, context) == [
        "ssh",
        "-F",
        str(context.config_file),
        node.alias,
    ]


def test_pinned_context_rejects_broad_or_symlink_directory(tmp_path):
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o700)
    unsafe.chmod(0o755)
    identity = unsafe / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)

    with pytest.raises(RuntimeError, match="directory"):
        module.create_context(unsafe, identity)

    unsafe.chmod(0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(unsafe, target_is_directory=True)
    with pytest.raises(RuntimeError, match="directory"):
        module.create_context(linked, identity)


def test_remote_maintenance_executor_has_literal_minimal_environment():
    tree = ast.parse(
        module.REMOTE_MAINTENANCE_EXECUTOR,
        "<remote-maintenance-executor>",
    )
    environment_assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "environment"
            for target in node.targets
        )
    ]
    assert len(environment_assignments) == 1
    environment = environment_assignments[0].value
    assert isinstance(environment, ast.Dict)
    assert {key.value for key in environment.keys if isinstance(key, ast.Constant)} == {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "DOCKER_CONTEXT",
        "PROJECT_DIR",
        "COMPOSE_FILE",
        "PITR_PROVISION_MODE",
    }
    assert "os.environ" not in module.REMOTE_MAINTENANCE_EXECUTOR
    assert "activate-archive" not in module.REMOTE_MAINTENANCE_EXECUTOR
    assert "docker-compose.prod.yml" not in module.REMOTE_MAINTENANCE_EXECUTOR


def test_fenced_primary_provision_has_narrow_fail_closed_proofs():
    source = pitr_remote_executors.LOCKED_MAINTENANCE_WRAPPER
    ast.parse(source, "<locked-maintenance-wrapper>")
    assert 'expected = b"fencing\\n"' in source
    assert "before.st_uid != 0" in source
    assert "before.st_gid != 0" in source
    assert "before.st_nlink != 1" in source
    assert "stat.S_IMODE(before.st_mode) != 0o600" in source
    assert "os.O_NOFOLLOW" in source
    assert 'result.stdout.strip() != "inactive"' in source
    assert '"ps",\n            "--all",\n            "-q"' in source
    assert "primary fenced runtime still has API or bot containers" in source
    assert 'if provision_mode == "fenced":' in source


@pytest.mark.parametrize("phase", ["restore-drill", "verify"])
def test_public_maintenance_phase_is_topology_guarded_and_uses_root_txid(
    tmp_path, monkeypatch, phase
):
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)
    calls = []
    topologies = [_topology(), _topology()]

    monkeypatch.setattr(module, "create_context", lambda *_args: object())
    monkeypatch.setattr(module, "validate_effective_config", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "discover_cluster_topology",
        lambda **_kwargs: topologies.pop(0),
    )
    monkeypatch.setattr(
        module,
        "run_remote_maintenance_phase",
        lambda **kwargs: calls.append(kwargs),
    )

    assert module.main(
        [
            "--phase",
            phase,
            "--transaction-id",
            TXID,
            "--identity-file",
            str(identity),
            "--no-prompt",
        ]
    ) == 0
    assert not topologies
    assert len(calls) == 1
    assert calls[0]["node"].alias == "mvn-api"
    assert calls[0]["phase"] == phase
    assert calls[0]["transaction_id"] == TXID


@pytest.mark.parametrize(
    ("after", "field"),
    [
        (_topology(timeline=10), "timeline"),
        (_topology(primary=1), "primary"),
        (_topology(system_identifier="8423456789012345678"), "system_identifier"),
    ],
)
def test_public_maintenance_detects_topology_drift_after_attempt(
    tmp_path, monkeypatch, after, field, capsys
):
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)
    topologies = [_topology(), after]

    monkeypatch.setattr(module, "create_context", lambda *_args: object())
    monkeypatch.setattr(module, "validate_effective_config", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "discover_cluster_topology",
        lambda **_kwargs: topologies.pop(0),
    )
    monkeypatch.setattr(module, "run_remote_maintenance_phase", lambda **_kwargs: None)

    assert module.main(
        [
            "--phase",
            "verify",
            "--transaction-id",
            TXID,
            "--identity-file",
            str(identity),
        ]
    ) == 1
    assert field in capsys.readouterr().out


def test_public_maintenance_preserves_action_and_topology_failure(tmp_path, monkeypatch, capsys):
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)
    topologies = [_topology(), _topology(timeline=10)]
    monkeypatch.setattr(module, "create_context", lambda *_args: object())
    monkeypatch.setattr(module, "validate_effective_config", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "discover_cluster_topology",
        lambda **_kwargs: topologies.pop(0),
    )
    monkeypatch.setattr(
        module,
        "run_remote_maintenance_phase",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("remote failed")),
    )

    assert module.main(
        [
            "--phase",
            "verify",
            "--transaction-id",
            TXID,
            "--identity-file",
            str(identity),
        ]
    ) == 1
    output = capsys.readouterr().out
    assert "remote failed" in output
    assert "topology proof" in output


def test_remote_phase_function_rejects_activation_even_with_txid(tmp_path):
    with pytest.raises(RuntimeError, match="unsupported maintenance phase"):
        module.run_remote_maintenance_phase(
            node=module.PATRONI_NODES[0],
            context=_context(tmp_path),
            bootstrap_helper=module.DEFAULT_BOOTSTRAP_HELPER,
            phase="activate-archive",
            transaction_id=TXID,
        )
    with pytest.raises(SystemExit):
        module.parse_args(["--phase", "activate-archive"])
