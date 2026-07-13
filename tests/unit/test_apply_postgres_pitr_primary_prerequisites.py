import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/ha/apply_postgres_pitr_primary_prerequisites.py"


spec = importlib.util.spec_from_file_location("apply_postgres_pitr_primary_prerequisites", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeCompleted:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _env(**overrides):
    values = {
        "POSTGRES_PITR_CLUSTER": "mvn-api",
        "POSTGRES_PITR_S3_BUCKET": "mvn-postgres-pitr",
        "POSTGRES_PITR_S3_ENDPOINT_URL": "https://account-id.r2.cloudflarestorage.com",
        "POSTGRES_PITR_S3_REGION": "auto",
        "POSTGRES_PITR_S3_ACCESS_KEY_ID": "access-key-id",
        "POSTGRES_PITR_S3_SECRET_ACCESS_KEY": "super-secret-key",
        "POSTGRES_PITR_S3_KEY_PREFIX": "postgres/pitr",
    }
    values.update(overrides)
    return values


def _context(tmp_path):
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)
    return module.create_context(tmp_path, identity)


def _patroni_payload(node, role):
    return json.dumps({"state": "running", "role": role, "name": node.alias})


def _role_from_ssh_args(args):
    if "mvn-api" in args:
        return "leader"
    if "zakup" in args:
        return "replica"
    raise AssertionError(f"unknown pinned target: {args}")


def test_render_env_redacts_access_keys():
    config = module.collect_inputs(environ=_env(), no_prompt=True)

    rendered = module.render_env(config, redact=True)

    assert "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr" in rendered
    assert "access-key-id" not in rendered
    assert "super-secret-key" not in rendered
    assert "POSTGRES_PITR_S3_ACCESS_KEY_ID=redacted" in rendered
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=redacted" in rendered


def test_load_env_file_loads_only_pitr_keys_without_overriding(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr",
                "POSTGRES_PITR_S3_ENDPOINT_URL='https://account-id.r2.cloudflarestorage.com'",
                "POSTGRES_PITR_S3_ACCESS_KEY_ID=access-key-id",
                "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key",
                "GH_TOKEN=stale-github-token",
                "CLOUDFLARE_API_TOKEN_LB_AUDIT=cloudflare-token",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    monkeypatch.setenv("POSTGRES_PITR_S3_BUCKET", "existing-bucket")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN_LB_AUDIT", raising=False)

    module.load_env_file(env_file)

    assert module._env("POSTGRES_PITR_S3_BUCKET", module.os.environ) == "existing-bucket"
    assert (
        module._env("POSTGRES_PITR_S3_ENDPOINT_URL", module.os.environ)
        == "https://account-id.r2.cloudflarestorage.com"
    )
    assert module._env("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", module.os.environ) == "super-secret-key"
    assert module._env("GH_TOKEN", module.os.environ) == ""
    assert module._env("CLOUDFLARE_API_TOKEN_LB_AUDIT", module.os.environ) == ""


def test_load_env_file_rejects_broad_mode_symlink_and_wrong_owner(
    tmp_path, monkeypatch
):
    insecure = tmp_path / "insecure.env"
    insecure.write_text("POSTGRES_PITR_S3_BUCKET=bucket\n", encoding="utf-8")
    insecure.chmod(0o644)
    with pytest.raises(RuntimeError, match="group or other"):
        module.load_env_file(insecure)

    secure = tmp_path / "secure.env"
    secure.write_text("POSTGRES_PITR_S3_BUCKET=bucket\n", encoding="utf-8")
    secure.chmod(0o600)
    link = tmp_path / "linked.env"
    link.symlink_to(secure)
    with pytest.raises(RuntimeError, match="non-symlink"):
        module.load_env_file(link)

    monkeypatch.setattr(module.os, "geteuid", lambda: secure.stat().st_uid + 1)
    with pytest.raises(RuntimeError, match="current user"):
        module.load_env_file(secure)


def test_remote_secret_phase_uses_memfd_lock_and_pinned_ssh_stdin(tmp_path):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    config = module.collect_inputs(environ=_env(), no_prompt=True)
    env_text = module.render_env(config)
    context = _context(tmp_path)

    module.run_remote_secret_phase(
        node=module.PATRONI_NODES[0],
        context=context,
        env_text=env_text,
        bootstrap_helper="/usr/local/sbin/mvn-postgres-pitr-bootstrap",
        phase="preflight",
        runner=fake_runner,
    )

    args, stdin = calls[0]
    assert args[0:2] == ["ssh", "-F"]
    assert args[2] == str(context.config_file)
    assert args[-2] == "mvn-api"
    effective_config = context.config_file.read_text(encoding="utf-8")
    assert "StrictHostKeyChecking yes" in effective_config
    assert "KnownHostsCommand none" in effective_config
    assert "ControlMaster no" in effective_config
    assert "ControlPath none" in effective_config
    assert "PermitLocalCommand no" in effective_config
    assert "HostKeyAlias mvn-api" in effective_config
    assert "HostName 185.250.45.54" in effective_config
    assert "python3 -I -c" in args[-1]
    assert "memfd_create" in args[-1]
    assert "fcntl.flock" in args[-1]
    assert "pass_fds=(secret_fd, lock_fd)" in args[-1]
    assert "O_NOFOLLOW" in args[-1]
    assert '"ENV_INPUT_FILE": f"/proc/self/fd/{secret_fd}"' in args[-1]
    assert "/root/mvn-postgres-pitr.env" not in args[-1]
    assert "/opt/air-api" in args[-1]
    assert "docker-compose.patroni.yml" in args[-1]
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=super-secret-key" in stdin
    assert all("super-secret-key" not in arg for arg in args)


def test_remote_secret_executor_is_valid_isolated_python():
    compile(module.REMOTE_SECRET_EXECUTOR, "<remote-secret-executor>", "exec")
    assert "shell=True" not in module.REMOTE_SECRET_EXECUTOR
    assert "mktemp" not in module.REMOTE_SECRET_EXECUTOR
    assert "MAX_PAYLOAD_BYTES = 65536" in module.REMOTE_SECRET_EXECUTOR


def test_cleanup_removes_legacy_disk_env_through_pinned_alias(tmp_path):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        return FakeCompleted()

    module.cleanup_remote_env(
        node=module.PATRONI_NODES[0],
        context=_context(tmp_path),
        remote_env_file="/root/mvn-postgres-pitr.env",
        runner=fake_runner,
    )

    args, stdin = calls[0]
    assert stdin is None
    assert args[0:2] == ["ssh", "-F"]
    assert args[-2] == "mvn-api"
    assert args[-1] == "rm -f -- /root/mvn-postgres-pitr.env"


def test_discover_primary_probes_both_pinned_nodes_and_selects_promoted_reserve(
    tmp_path,
):
    calls = []

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        if "mvn-api" in args:
            return FakeCompleted(
                stdout=_patroni_payload(module.PATRONI_NODES[0], "replica")
            )
        return FakeCompleted(
            stdout=_patroni_payload(module.PATRONI_NODES[1], "leader")
        )

    selected = module.discover_primary(
        context=_context(tmp_path), runner=fake_runner
    )

    assert selected.alias == "zakup"
    assert selected.project_dir == "/opt/mvn-reserve"
    assert selected.compose_file == "docker-compose.patroni.yml"
    assert len(calls) == 2
    assert all(call[0][0:2] == ["ssh", "-F"] for call in calls)


def test_discover_primary_rejects_split_brain(tmp_path):
    def fake_runner(args, stdin):
        node = (
            module.PATRONI_NODES[0]
            if "mvn-api" in args
            else module.PATRONI_NODES[1]
        )
        return FakeCompleted(stdout=_patroni_payload(node, "leader"))

    with pytest.raises(RuntimeError, match="unsafe Patroni topology"):
        module.discover_primary(context=_context(tmp_path), runner=fake_runner)


@pytest.mark.parametrize(
    "unsafe_flag",
    [
        "pending_restart",
        "pause",
        "cluster_unlocked",
        "failsafe_mode_is_active",
    ],
)
def test_patroni_role_rejects_unsafe_cluster_flags(unsafe_flag):
    node = module.PATRONI_NODES[0]
    payload = {
        "state": "running",
        "role": "leader",
        "name": node.alias,
        unsafe_flag: True,
    }

    with pytest.raises(RuntimeError, match="Patroni reports"):
        module._patroni_role(payload, node)


def test_patroni_role_requires_exact_nonempty_node_identity():
    node = module.PATRONI_NODES[0]

    with pytest.raises(RuntimeError, match="<empty>"):
        module._patroni_role({"state": "running", "role": "leader"}, node)


def test_identity_file_must_be_owner_only_regular_non_symlink(tmp_path):
    insecure = tmp_path / "insecure"
    insecure.write_text("key", encoding="utf-8")
    insecure.chmod(0o644)
    with pytest.raises(RuntimeError, match="group or other"):
        module.validate_identity_file(str(insecure))

    secure = tmp_path / "secure"
    secure.write_text("key", encoding="utf-8")
    secure.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(secure)
    with pytest.raises(RuntimeError, match="non-symlink"):
        module.validate_identity_file(str(link))


def test_generated_config_resolves_alias_to_one_effective_identity(tmp_path):
    context = _context(tmp_path)
    node = module.PATRONI_NODES[0]

    result = module.subprocess.run(
        ["ssh", "-G", "-F", str(context.config_file), node.alias],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    effective: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(" ")
        effective.setdefault(key, []).append(value)
    assert effective["hostname"] == [node.physical_host]
    assert effective["user"] == [node.user]
    assert effective["hostkeyalias"] == [node.alias]
    assert effective["identityfile"] == [str(context.identity_file)]
    assert effective["identitiesonly"] == ["yes"]
    assert effective["stricthostkeychecking"] == ["true"]
    assert effective["userknownhostsfile"] == [str(context.known_hosts_file)]

    args = module.ssh_args(node, context)
    assert args == ["ssh", "-F", str(context.config_file), node.alias]
    assert node.physical_host not in args


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


@pytest.mark.parametrize(
    "unsafe_option",
    [
        "--ssh-host",
        "--project-dir",
        "--compose-file",
        "--remote-env-file",
        "--bootstrap-helper",
    ],
)
def test_unsafe_remote_overrides_are_rejected(unsafe_option):
    with pytest.raises(SystemExit):
        module.parse_args([unsafe_option, "203.0.113.5"])


def test_collect_inputs_reports_missing_names_without_secret_values():
    try:
        module.collect_inputs(
            environ=_env(POSTGRES_PITR_S3_BUCKET="", POSTGRES_PITR_S3_SECRET_ACCESS_KEY="super-secret-key"),
            no_prompt=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("collect_inputs should fail")

    assert "POSTGRES_PITR_S3_BUCKET" in message
    assert "super-secret-key" not in message


def test_collect_inputs_rejects_public_endpoint():
    try:
        module.collect_inputs(
            environ=_env(POSTGRES_PITR_S3_ENDPOINT_URL="https://cdn.mvn.by"),
            no_prompt=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("collect_inputs should fail")

    assert "r2.cloudflarestorage.com" in message
    assert "super-secret-key" not in message


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://legit.r2.cloudflarestorage.com.evil.example",
        "https://evil.example/path/.r2.cloudflarestorage.com",
        "https://user@account-id.r2.cloudflarestorage.com",
        "https://account-id.r2.cloudflarestorage.com/bucket",
        "https://account-id.r2.cloudflarestorage.com?redirect=evil",
        "https://account-id.r2.cloudflarestorage.com#fragment",
        "http://account-id.r2.cloudflarestorage.com",
        "https://account-id.r2.cloudflarestorage.com:444",
        "https://r2.cloudflarestorage.com",
        "https://extra.account-id.r2.cloudflarestorage.com",
    ],
)
def test_collect_inputs_rejects_endpoint_spoofing(endpoint):
    with pytest.raises(RuntimeError) as error:
        module.collect_inputs(
            environ=_env(POSTGRES_PITR_S3_ENDPOINT_URL=endpoint),
            no_prompt=True,
        )

    assert "super-secret-key" not in str(error.value)


def test_collect_inputs_allows_explicit_https_default_port():
    config = module.collect_inputs(
        environ=_env(
            POSTGRES_PITR_S3_ENDPOINT_URL=(
                "https://account-id.r2.cloudflarestorage.com:443/"
            )
        ),
        no_prompt=True,
    )

    assert config.endpoint_url.endswith(":443/")


def test_dry_run_prints_redacted_env(monkeypatch, capsys):
    monkeypatch.setenv("POSTGRES_PITR_CLUSTER", "mvn-api")
    monkeypatch.setenv("POSTGRES_PITR_S3_BUCKET", "mvn-postgres-pitr")
    monkeypatch.setenv("POSTGRES_PITR_S3_ENDPOINT_URL", "https://account-id.r2.cloudflarestorage.com")
    monkeypatch.setenv("POSTGRES_PITR_S3_REGION", "auto")
    monkeypatch.setenv("POSTGRES_PITR_S3_ACCESS_KEY_ID", "access-key-id")
    monkeypatch.setenv("POSTGRES_PITR_S3_SECRET_ACCESS_KEY", "super-secret-key")
    monkeypatch.setenv("POSTGRES_PITR_S3_KEY_PREFIX", "postgres/pitr")

    assert module.main(["--dry-run", "--no-prompt"]) == 0

    output = capsys.readouterr().out
    assert "POSTGRES_PITR_S3_BUCKET=mvn-postgres-pitr" in output
    assert "access-key-id" not in output
    assert "super-secret-key" not in output
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY=redacted" in output


def test_probe_only_requires_no_pitr_secrets_and_makes_no_mutation(
    tmp_path, monkeypatch
):
    calls = []
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        node = (
            module.PATRONI_NODES[0]
            if "mvn-api" in args
            else module.PATRONI_NODES[1]
        )
        return FakeCompleted(stdout=_patroni_payload(node, _role_from_ssh_args(args)))

    for name in _env():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--probe-only", "--identity-file", str(identity)]) == 0
    assert len(calls) == 2
    assert all(stdin is None for _args, stdin in calls)
    assert all(args[-1].startswith("curl ") for args, _stdin in calls)


def test_main_probes_cleans_legacy_files_then_runs_in_memory_secret_phase(
    tmp_path, monkeypatch
):
    calls = []
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        if args[-1].startswith("curl "):
            node = (
                module.PATRONI_NODES[0]
                if "mvn-api" in args
                else module.PATRONI_NODES[1]
            )
            return FakeCompleted(stdout=_patroni_payload(node, _role_from_ssh_args(args)))
        return FakeCompleted()

    for name, value in _env().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert (
        module.main(
            [
                "--no-prompt",
                "--phase",
                "preflight",
                "--identity-file",
                str(identity),
            ]
        )
        == 0
    )

    assert len(calls) == 5
    assert calls[0][0][-1].startswith("curl ")
    assert calls[1][0][-1].startswith("curl ")
    assert calls[2][0][-1] == "rm -f -- /root/mvn-postgres-pitr.env"
    assert calls[3][0][-1] == "rm -f -- /root/mvn-postgres-pitr.env"
    assert "super-secret-key" in calls[4][1]
    assert all("super-secret-key" not in arg for args, _stdin in calls for arg in args)
    assert "python3 -I -c" in calls[4][0][-1]
    assert "preflight" in calls[4][0][-1]
    assert "/root/mvn-postgres-pitr.env" not in calls[4][0][-1]


def test_main_refuses_cluster_name_that_does_not_match_promoted_primary(
    tmp_path, monkeypatch
):
    calls = []
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        node = (
            module.PATRONI_NODES[0]
            if "mvn-api" in args
            else module.PATRONI_NODES[1]
        )
        role = "replica" if node.alias == "mvn-api" else "leader"
        return FakeCompleted(stdout=_patroni_payload(node, role))

    for name, value in _env(POSTGRES_PITR_CLUSTER="mvn-api").items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert (
        module.main(["--no-prompt", "--identity-file", str(identity)])
        == 1
    )
    assert len(calls) == 2
    assert all(stdin is None for _args, stdin in calls)


def test_main_secret_phase_failure_leaves_no_disk_secret_path(
    tmp_path, monkeypatch
):
    calls = []
    failed_once = False
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)

    def fake_runner(args, stdin):
        nonlocal failed_once
        calls.append((list(args), stdin))
        if args[-1].startswith("curl "):
            node = (
                module.PATRONI_NODES[0]
                if "mvn-api" in args
                else module.PATRONI_NODES[1]
            )
            return FakeCompleted(stdout=_patroni_payload(node, _role_from_ssh_args(args)))
        if "python3 -I -c" in args[-1] and not failed_once:
            failed_once = True
            return FakeCompleted(returncode=23, stderr="simulated remote failure")
        return FakeCompleted()

    for name, value in _env().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    result = module.main(
        ["--no-prompt", "--identity-file", str(identity), "--phase", "preflight"]
    )

    assert result == 1
    assert failed_once is True
    assert "python3 -I -c" in calls[-1][0][-1]
    assert "/root/mvn-postgres-pitr.env" not in calls[-1][0][-1]
    assert "mvn-api" in calls[-1][0]
    assert "super-secret-key" in calls[-1][1]
    assert all("super-secret-key" not in arg for args, _stdin in calls for arg in args)


def test_main_refuses_secret_transfer_when_legacy_cleanup_fails(
    tmp_path, monkeypatch
):
    calls = []
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        if args[-1].startswith("curl "):
            node = (
                module.PATRONI_NODES[0]
                if "mvn-api" in args
                else module.PATRONI_NODES[1]
            )
            return FakeCompleted(stdout=_patroni_payload(node, _role_from_ssh_args(args)))
        return FakeCompleted(returncode=23, stderr="simulated cleanup failure")

    for name, value in _env().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert module.main(["--no-prompt", "--identity-file", str(identity)]) == 1
    assert len(calls) == 3
    assert all(stdin is None for _args, stdin in calls)


def test_main_can_load_project_env_file(tmp_path, monkeypatch):
    calls = []
    identity = tmp_path / "identity"
    identity.write_text("test-private-key", encoding="utf-8")
    identity.chmod(0o600)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(f"{name}={value}" for name, value in _env().items()),
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    def fake_runner(args, stdin):
        calls.append((list(args), stdin))
        if args[-1].startswith("curl "):
            node = (
                module.PATRONI_NODES[0]
                if "mvn-api" in args
                else module.PATRONI_NODES[1]
            )
            return FakeCompleted(stdout=_patroni_payload(node, _role_from_ssh_args(args)))
        return FakeCompleted()

    for name in _env():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module, "_run_subprocess", fake_runner)

    assert (
        module.main(
            [
                "--no-prompt",
                "--phase",
                "preflight",
                "--env-file",
                str(env_file),
                "--identity-file",
                str(identity),
            ]
        )
        == 0
    )

    assert len(calls) == 5
    assert "super-secret-key" in calls[4][1]
    assert all("super-secret-key" not in arg for args, _stdin in calls for arg in args)
