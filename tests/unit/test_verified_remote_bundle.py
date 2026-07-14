from argparse import Namespace
from pathlib import Path

import pytest

from scripts.ha import run_verified_remote_bundle as bundle


def _args(tmp_path: Path, files: list[Path]) -> Namespace:
    identity = tmp_path / "identity"
    known_hosts = tmp_path / "known_hosts"
    identity.write_text("key", encoding="utf-8")
    known_hosts.write_text("host key", encoding="utf-8")
    identity.chmod(0o600)
    known_hosts.chmod(0o600)
    return Namespace(
        remote="root@example.test",
        prefix="mvn-backend-deploy",
        entry=files[0].name,
        files=[str(path) for path in files],
        identity_file=str(identity),
        known_hosts_file=str(known_hosts),
        print_required=["summary.txt"],
        print_optional=[],
        env=["API_PROJECT_DIR=/opt/air-api"],
        secret_env="",
    )


def test_remote_command_verifies_exact_bundle_before_secret_and_entry():
    command = bundle.remote_command(
        bundle="/tmp/mvn-backend-deploy.ABC12345",
        manifest="manifest",
        verifier="verifier source",
        entry="deploy.sh",
        environment={"API_HELPER": "__MVN_BUNDLE__/helper.py"},
        secret_name="GHCR_PAT",
        required=["summary.txt"],
        optional=[],
    )

    assert command.index("python3 -I -c") < command.index("IFS= read -r GHCR_PAT")
    assert command.index("IFS= read -r GHCR_PAT") < command.index("bash")
    assert "GHCR_PAT=" not in command
    assert "/tmp/mvn-backend-deploy.ABC12345/helper.py" in command
    assert "trap 'rm -rf -- /tmp/mvn-backend-deploy.ABC12345' EXIT" in command
    assert command.rindex("python3 -I -c") < command.rindex("cat")
    assert "unsafe remote bundle output" in command


def test_local_inputs_reject_duplicate_source_name_and_symlinked_ssh_input(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(bundle, "REPO_ROOT", tmp_path)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "deploy.sh"
    second = second_dir / "deploy.sh"
    first.write_text("exit 0\n", encoding="utf-8")
    second.write_text("exit 0\n", encoding="utf-8")
    first.chmod(0o755)
    second.chmod(0o755)
    args = _args(tmp_path, [first, second])
    with pytest.raises(RuntimeError, match="missing or duplicated"):
        bundle.validate_local_inputs(args)

    args.files = [str(first)]
    args.secret_env = "GHCR_PAT;touch /tmp/injected"
    with pytest.raises(RuntimeError, match="secret environment name is invalid"):
        bundle.validate_local_inputs(args)
    args.secret_env = "GHCR_PAT"
    identity = Path(args.identity_file)
    target = tmp_path / "real-key"
    identity.rename(target)
    identity.symlink_to(target)
    with pytest.raises(RuntimeError, match="SSH input metadata is unsafe"):
        bundle.validate_local_inputs(args)


def test_runner_uses_random_root_private_bundle_and_inline_reviewed_verifier():
    source = Path(bundle.__file__).read_text(encoding="utf-8")
    assert "test \\\"$(id -u)\\\" -eq 0" in source
    assert "mktemp -d /tmp/{args.prefix}.XXXXXXXX" in source
    assert "create_manifest(sources)" in source
    assert "python3\", \"-I\", \"-c" in source
    assert len(source.splitlines()) < 700
