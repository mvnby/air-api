"""Fail-closed SSH inventory and configuration for secret-bearing PITR setup."""

from __future__ import annotations

import base64
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PatroniNode:
    alias: str
    physical_host: str
    user: str
    project_dir: str
    compose_file: str
    compose_source: Path
    host_key_source: Path


@dataclass(frozen=True)
class PinnedSshContext:
    identity_file: Path
    known_hosts_file: Path
    config_file: Path


PATRONI_NODES = (
    PatroniNode(
        alias="mvn-api",
        physical_host="185.250.45.54",
        user="root",
        project_dir="/opt/air-api",
        compose_file="docker-compose.patroni.yml",
        compose_source=REPO_ROOT / "deploy/ha/mvn-api/docker-compose.patroni.yml",
        host_key_source=REPO_ROOT / "deploy/ha/security/mvn-api-ssh-host-key.pub",
    ),
    PatroniNode(
        alias="zakup",
        physical_host="193.47.42.213",
        user="root",
        project_dir="/opt/mvn-reserve",
        compose_file="docker-compose.patroni.yml",
        compose_source=REPO_ROOT / "deploy/ha/zakup/docker-compose.patroni.yml",
        host_key_source=REPO_ROOT / "deploy/ha/security/zakup-ssh-host-key.pub",
    ),
)


def ssh_subprocess_environment() -> dict[str, str]:
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "USER", "LOGNAME", "TMPDIR")
    environment = {name: os.environ[name] for name in allowed if os.environ.get(name)}
    environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    environment.setdefault("HOME", str(Path.home()))
    environment.setdefault("LANG", "C")
    environment.setdefault("LC_ALL", "C")
    return environment


def _read_ssh_wire_string(blob: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 4 > len(blob):
        raise ValueError("truncated SSH key")
    size = int.from_bytes(blob[offset : offset + 4], "big")
    start = offset + 4
    end = start + size
    if end > len(blob):
        raise ValueError("truncated SSH key")
    return blob[start:end], end


def _read_pinned_host_key(path: Path) -> tuple[str, str]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"tracked SSH host key is missing: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("tracked SSH host key must be a regular non-symlink file")
    if metadata.st_uid != os.geteuid():
        raise RuntimeError("tracked SSH host key must be owned by the current user")
    if metadata.st_mode & 0o022:
        raise RuntimeError("tracked SSH host key must not be group/world writable")
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise RuntimeError("tracked SSH host key must contain exactly one line")
    fields = lines[0].split()
    if len(fields) != 2 or fields[0] != "ssh-ed25519":
        raise RuntimeError("tracked SSH host key must be one Ed25519 key without a comment")
    try:
        blob = base64.b64decode(fields[1], validate=True)
        key_type, offset = _read_ssh_wire_string(blob, 0)
        public_key, offset = _read_ssh_wire_string(blob, offset)
    except (ValueError, IndexError) as exc:
        raise RuntimeError("tracked SSH host key is invalid") from exc
    if key_type != b"ssh-ed25519" or len(public_key) != 32 or offset != len(blob):
        raise RuntimeError("tracked SSH host key is invalid")
    return fields[0], fields[1]


def render_known_hosts(nodes: Sequence[PatroniNode] = PATRONI_NODES) -> str:
    lines = []
    for node in nodes:
        key_type, key_value = _read_pinned_host_key(node.host_key_source)
        lines.append(f"{node.alias} {key_type} {key_value}")
    return "\n".join(lines) + "\n"


def _safe_ssh_path(path: Path) -> str:
    rendered = str(path)
    if not re.fullmatch(r"(?:/[A-Za-z0-9._-]+)+", rendered):
        raise RuntimeError("SSH paths must be absolute and contain only safe characters")
    return rendered


def render_ssh_config(
    *,
    identity_file: Path,
    known_hosts_file: Path,
    nodes: Sequence[PatroniNode] = PATRONI_NODES,
) -> str:
    identity = _safe_ssh_path(identity_file)
    known_hosts = _safe_ssh_path(known_hosts_file)
    aliases = " ".join(node.alias for node in nodes)
    lines: list[str] = []
    for node in nodes:
        lines.extend(
            [
                f"Host {node.alias}",
                f"  HostName {node.physical_host}",
                f"  User {node.user}",
                f"  HostKeyAlias {node.alias}",
            ]
        )
    lines.extend(
        [
            f"Host {aliases}",
            "  Port 22",
            f"  IdentityFile {identity}",
            "  IdentitiesOnly yes",
            "  IdentityAgent none",
            "  AddKeysToAgent no",
            "  BatchMode yes",
            "  PreferredAuthentications publickey",
            "  PubkeyAuthentication yes",
            "  HostbasedAuthentication no",
            "  GSSAPIAuthentication no",
            "  PasswordAuthentication no",
            "  KbdInteractiveAuthentication no",
            "  NumberOfPasswordPrompts 0",
            "  StrictHostKeyChecking yes",
            "  GlobalKnownHostsFile /dev/null",
            f"  UserKnownHostsFile {known_hosts}",
            "  KnownHostsCommand none",
            "  HostKeyAlgorithms ssh-ed25519",
            "  UpdateHostKeys no",
            "  VerifyHostKeyDNS no",
            "  CanonicalizeHostname no",
            "  CheckHostIP no",
            "  ProxyCommand none",
            "  ProxyJump none",
            "  ControlMaster no",
            "  ControlPath none",
            "  ControlPersist no",
            "  PermitLocalCommand no",
            "  ClearAllForwardings yes",
            "  ForwardAgent no",
            "  ForwardX11 no",
            "  ConnectTimeout 20",
            "  ServerAliveInterval 15",
            "  ServerAliveCountMax 3",
            "  RequestTTY no",
            "Host *",
            "  HostName invalid.invalid",
            "  User invalid",
            "  IdentitiesOnly yes",
            "  IdentityAgent none",
            "  BatchMode yes",
            "  StrictHostKeyChecking yes",
            "  GlobalKnownHostsFile /dev/null",
            f"  UserKnownHostsFile {known_hosts}",
            "  KnownHostsCommand none",
            "  HostKeyAlgorithms ssh-ed25519",
            "  UpdateHostKeys no",
            "  VerifyHostKeyDNS no",
            "  CanonicalizeHostname no",
            "  ProxyCommand /bin/false",
            "  ProxyJump none",
            "  ControlMaster no",
            "  PermitLocalCommand no",
            "  ClearAllForwardings yes",
            "  ForwardAgent no",
            "  ForwardX11 no",
            "  RequestTTY no",
            "",
        ]
    )
    return "\n".join(lines)


def create_context(directory: Path, identity_file: Path) -> PinnedSshContext:
    directory_metadata = directory.lstat()
    identity_metadata = identity_file.lstat()
    if (
        stat.S_ISLNK(directory_metadata.st_mode)
        or not stat.S_ISDIR(directory_metadata.st_mode)
        or directory_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(directory_metadata.st_mode) & 0o077
    ):
        raise RuntimeError("pinned SSH directory must be owner-only and non-symlink")
    if (
        stat.S_ISLNK(identity_metadata.st_mode)
        or not stat.S_ISREG(identity_metadata.st_mode)
        or identity_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(identity_metadata.st_mode) & 0o077
    ):
        raise RuntimeError("SSH identity must be owner-only and non-symlink")
    known_hosts_file = directory / "known_hosts"
    config_file = directory / "config"
    known_hosts_file.write_text(render_known_hosts(), encoding="utf-8")
    known_hosts_file.chmod(0o600)
    config_file.write_text(
        render_ssh_config(
            identity_file=identity_file,
            known_hosts_file=known_hosts_file,
        ),
        encoding="utf-8",
    )
    config_file.chmod(0o600)
    return PinnedSshContext(
        identity_file=identity_file,
        known_hosts_file=known_hosts_file,
        config_file=config_file,
    )


def ssh_args(node: PatroniNode, context: PinnedSshContext) -> list[str]:
    return ["ssh", "-F", str(context.config_file), node.alias]


def effective_config(node: PatroniNode, context: PinnedSshContext) -> dict[str, list[str]]:
    result = subprocess.run(
        ["ssh", "-G", "-F", str(context.config_file), node.alias],
        text=True,
        capture_output=True,
        check=False,
        env=ssh_subprocess_environment(),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ssh -G failed").strip()
        raise RuntimeError(f"could not validate pinned SSH config for {node.alias}: {detail}")
    parsed: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(" ")
        if separator:
            parsed.setdefault(key, []).append(value)
    return parsed


def validate_effective_config(node: PatroniNode, context: PinnedSshContext) -> None:
    config = effective_config(node, context)
    expected_singletons = {
        "hostname": node.physical_host,
        "user": node.user,
        "hostkeyalias": node.alias,
        "identityfile": str(context.identity_file),
        "identitiesonly": "yes",
        "stricthostkeychecking": "true",
        "userknownhostsfile": str(context.known_hosts_file),
        "globalknownhostsfile": "/dev/null",
        "hostkeyalgorithms": "ssh-ed25519",
        "batchmode": "yes",
        "passwordauthentication": "no",
        "kbdinteractiveauthentication": "no",
        "hostbasedauthentication": "no",
        "gssapiauthentication": "no",
        "identityagent": "none",
        "controlmaster": "false",
        "controlpersist": "no",
        "permitlocalcommand": "no",
        "clearallforwardings": "yes",
        "forwardagent": "no",
        "forwardx11": "no",
        "updatehostkeys": "false",
        "verifyhostkeydns": "false",
        "canonicalizehostname": "false",
        "checkhostip": "no",
        "requesttty": "false",
    }
    for name, expected in expected_singletons.items():
        actual = config.get(name, [])
        if actual != [expected]:
            raise RuntimeError(
                f"unsafe effective SSH config for {node.alias}: {name} must be exactly {expected}"
            )
    for forbidden in ("knownhostscommand", "proxycommand", "proxyjump", "controlpath"):
        if config.get(forbidden):
            raise RuntimeError(
                f"unsafe effective SSH config for {node.alias}: {forbidden} must be disabled"
            )
