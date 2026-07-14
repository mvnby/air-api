#!/usr/bin/env python3
"""Run reviewed deployment scripts from an exact private remote bundle."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import stat
import subprocess
import sys
from pathlib import Path

try:
    from scripts.ha.verify_patroni_remote_bundle import (
        _read_regular,
        create_manifest,
    )
except ModuleNotFoundError:
    from verify_patroni_remote_bundle import _read_regular, create_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts/ha/verify_patroni_remote_bundle.py"
REMOTE_RE = re.compile(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+")
PREFIX_RE = re.compile(r"mvn-[a-z0-9-]{1,48}")
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
BUNDLE_TOKEN = "__MVN_BUNDLE__"
OUTPUT_VERIFIER = r'''import os, stat, sys
for path in sys.argv[1:]:
    before = os.lstat(path)
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or before.st_uid != 0 or before.st_gid != 0 or before.st_nlink != 1
            or before.st_mode & 0o022 or before.st_size > 2097152):
        raise SystemExit("unsafe remote bundle output: " + path)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise SystemExit("remote bundle output changed while opening: " + path)
    finally:
        os.close(fd)
'''


def parse_environment(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        name, separator, content = value.partition("=")
        if not separator or not NAME_RE.fullmatch(name) or name in result:
            raise RuntimeError("remote bundle environment is invalid or duplicated")
        if "\0" in content or "\n" in content or "\r" in content:
            raise RuntimeError("remote bundle environment contains control data")
        result[name] = content
    return result


def ssh_options(identity: Path, known_hosts: Path) -> list[str]:
    return [
        "-F", "/dev/null", "-i", str(identity), "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "UpdateHostKeys=no", "-o", "ConnectTimeout=20",
        "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
    ]


def run_checked(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, check=False, text=True, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"remote bundle command failed with status {result.returncode}")
    return result


def validate_local_inputs(args: argparse.Namespace) -> tuple[list[Path], dict[str, str]]:
    if not REMOTE_RE.fullmatch(args.remote) or not PREFIX_RE.fullmatch(args.prefix):
        raise RuntimeError("remote bundle destination is invalid")
    if args.secret_env and not NAME_RE.fullmatch(args.secret_env):
        raise RuntimeError("remote bundle secret environment name is invalid")
    sources = [Path(value).resolve() for value in args.files]
    for path in sources:
        try:
            path.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise RuntimeError("remote bundle source is outside the reviewed repository") from exc
    names = [path.name for path in sources]
    if len(set(names)) != len(names) or args.entry not in names:
        raise RuntimeError("remote bundle entry is missing or duplicated")
    outputs = [*args.print_required, *args.print_optional]
    if any(not FILE_RE.fullmatch(name) for name in [args.entry, *outputs]):
        raise RuntimeError("remote bundle filename is invalid")
    if set(outputs).intersection(names) or len(set(outputs)) != len(outputs):
        raise RuntimeError("remote bundle output filename is unsafe")
    for path in (Path(args.identity_file), Path(args.known_hosts_file)):
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o077
        ):
            raise RuntimeError(f"SSH input metadata is unsafe: {path}")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise RuntimeError(f"SSH input changed while opening: {path}")
        finally:
            os.close(descriptor)
    return sources, parse_environment(args.env)


def remote_command(
    *,
    bundle: str,
    manifest: str,
    verifier: str,
    entry: str,
    environment: dict[str, str],
    secret_name: str,
    required: list[str],
    optional: list[str],
) -> str:
    lines = [
        "set -euo pipefail",
        f"trap {shlex.quote('rm -rf -- ' + bundle)} EXIT",
        " ".join(
            [
                "python3", "-I", "-c", shlex.quote(verifier), "verify",
                shlex.quote(bundle), shlex.quote(manifest),
            ]
        ),
    ]
    if secret_name:
        lines.extend(
            [
                f"IFS= read -r {secret_name}",
                f"export {secret_name}",
            ]
        )
    assignments = []
    for name, value in sorted(environment.items()):
        assignments.append(f"{name}={shlex.quote(value.replace(BUNDLE_TOKEN, bundle))}")
    lines.append(
        " ".join([*assignments, "bash", shlex.quote(f"{bundle}/{entry}")])
    )
    for name in required:
        path = f"{bundle}/{name}"
        lines.append(
            f"python3 -I -c {shlex.quote(OUTPUT_VERIFIER)} {shlex.quote(path)}"
        )
        lines.append(f"cat {shlex.quote(path)}")
    for name in optional:
        path = f"{bundle}/{name}"
        verify = f"python3 -I -c {shlex.quote(OUTPUT_VERIFIER)} {shlex.quote(path)}"
        lines.append(
            f"if [ -e {shlex.quote(path)} ] || [ -L {shlex.quote(path)} ]; "
            f"then {verify} && cat {shlex.quote(path)}; fi"
        )
    return "\n".join(lines)


def execute(args: argparse.Namespace) -> None:
    sources, environment = validate_local_inputs(args)
    manifest = create_manifest(sources)
    verifier = _read_regular(VERIFIER, owner=os.geteuid()).decode("utf-8")
    options = ssh_options(Path(args.identity_file), Path(args.known_hosts_file))
    create = (
        f"set -e; test \"$(id -u)\" -eq 0; umask 077; "
        f"mktemp -d /tmp/{args.prefix}.XXXXXXXX"
    )
    result = run_checked(
        ["ssh", *options, args.remote, create],
        capture_output=True,
        timeout=60,
    )
    bundle = result.stdout.strip()
    if not re.fullmatch(rf"/tmp/{re.escape(args.prefix)}[.][A-Za-z0-9]{{8}}", bundle):
        raise RuntimeError("remote private bundle path is invalid")
    try:
        run_checked(
            ["scp", *options, *map(str, sources), f"{args.remote}:{bundle}/"],
            timeout=180,
        )
        secret = ""
        if args.secret_env:
            secret = os.environ.get(args.secret_env, "")
            if not secret or any(character in secret for character in "\0\r\n"):
                raise RuntimeError("remote bundle secret input is missing or invalid")
        command = remote_command(
            bundle=bundle,
            manifest=manifest,
            verifier=verifier,
            entry=args.entry,
            environment=environment,
            secret_name=args.secret_env,
            required=args.print_required,
            optional=args.print_optional,
        )
        run_checked(
            ["ssh", *options, args.remote, command],
            input=(secret + "\n") if args.secret_env else None,
            timeout=args.timeout,
        )
    finally:
        subprocess.run(
            ["ssh", *options, args.remote, f"rm -rf -- {shlex.quote(bundle)}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--remote", required=True)
    result.add_argument("--identity-file", required=True)
    result.add_argument("--known-hosts-file", required=True)
    result.add_argument("--prefix", required=True)
    result.add_argument("--entry", required=True)
    result.add_argument("--secret-env", default="")
    result.add_argument("--env", action="append", default=[])
    result.add_argument("--print-required", action="append", default=[])
    result.add_argument("--print-optional", action="append", default=[])
    result.add_argument("--timeout", type=int, default=1800)
    result.add_argument("files", nargs="+")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.timeout < 1 or args.timeout > 3600:
        raise RuntimeError("remote bundle timeout is invalid")
    execute(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, UnicodeError) as exc:
        print(f"verified_remote_bundle status=failed error={exc}", file=sys.stderr)
        raise SystemExit(1)
