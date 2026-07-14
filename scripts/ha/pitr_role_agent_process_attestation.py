"""Clock-free process-generation proof for the remote PITR role-agent executor."""

from __future__ import annotations


REMOTE_ROLE_AGENT_PROCESS_ATTESTATION = r'''
def metadata_fingerprint(metadata):
    return tuple(
        getattr(metadata, name)
        for name in (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns",
        )
    )


def snapshot_role_generation(manifest):
    snapshot = []
    for path in sorted(ROLE_ASSET_MODES):
        content, metadata = read_root_file(path, mode=ROLE_ASSET_MODES[path])
        digest = hashlib.sha256(content).hexdigest()
        if digest != manifest[path]:
            raise RuntimeError(f"role-agent digest changed across restart: {path}")
        snapshot.append((path, digest, metadata_fingerprint(metadata)))
    environment, metadata = read_root_file(
        ROLE_ENV_PATH, mode=0o600, maximum=16384
    )
    snapshot.append((
        ROLE_ENV_PATH,
        hashlib.sha256(environment).hexdigest(),
        metadata_fingerprint(metadata),
    ))
    return tuple(snapshot)


def read_proc_file(path, maximum=131072):
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0:
            raise RuntimeError("role-agent process metadata is unsafe")
        content = os.read(descriptor, maximum + 1)
        if len(content) > maximum or os.read(descriptor, 1):
            raise RuntimeError("role-agent process metadata exceeds limit")
        return content
    finally:
        os.close(descriptor)


def process_start_ticks(pid):
    raw = read_proc_file(f"/proc/{pid}/stat", 8192).decode("ascii")
    boundary = raw.rfind(") ")
    fields = raw[boundary + 2:].split() if boundary > 0 else []
    if len(fields) <= 19 or not fields[19].isdigit():
        raise RuntimeError("role-agent process start metadata is invalid")
    return int(fields[19])


def attest_live_process(expected_environment):
    pid = checked([
        "/usr/bin/systemctl", "show", "--property=MainPID", "--value",
        ROLE_AGENT_UNIT,
    ])
    if re.fullmatch(r"[1-9][0-9]*", pid) is None:
        raise RuntimeError("role-agent MainPID is invalid")
    if read_proc_file(f"/proc/{pid}/cmdline", 4096) != (
        b"/usr/bin/python3\0/usr/local/sbin/mvn-patroni-role-agent\0"
    ):
        raise RuntimeError("live role-agent command line is unreviewed")
    live = {}
    for entry in read_proc_file(f"/proc/{pid}/environ").split(b"\0"):
        if not entry:
            continue
        try:
            name, value = entry.decode("utf-8").split("=", 1)
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError("live role-agent environment is invalid") from exc
        if name.startswith("HA_"):
            if name in live:
                raise RuntimeError("live role-agent environment has a duplicate key")
            live[name] = value
    if live != expected_environment:
        raise RuntimeError("live role-agent environment differs from the reviewed contract")
    start_ticks = process_start_ticks(pid)
    if checked([
        "/usr/bin/systemctl", "show", "--property=MainPID", "--value",
        ROLE_AGENT_UNIT,
    ]) != pid:
        raise RuntimeError("role-agent MainPID changed during attestation")
    return pid, start_ticks


def prove_live_generation(
    expected_environment,
    manifest,
    generation,
    boundary,
    *,
    expected_enabled="enabled",
):
    if unit_state("is-active") != "active":
        raise RuntimeError(f"role-agent is not active after {boundary}")
    if unit_state("is-enabled") != expected_enabled:
        raise RuntimeError(
            f"role-agent enablement differs after {boundary}: "
            f"expected={expected_enabled}"
        )
    attest_loaded_unit()
    identity = attest_live_process(expected_environment)
    if snapshot_role_generation(manifest) != generation:
        raise RuntimeError(f"role-agent generation changed across {boundary}")
    return identity


def refresh_live_process(
    expected_environment,
    manifest,
    *,
    expected_enabled="enabled",
):
    before = snapshot_role_generation(manifest)
    old_pid, old_start_ticks = attest_live_process(expected_environment)
    checked(["/usr/bin/systemctl", "restart", ROLE_AGENT_UNIT])
    new_pid, new_start_ticks = prove_live_generation(
        expected_environment,
        manifest,
        before,
        "controlled restart",
        expected_enabled=expected_enabled,
    )
    if new_pid == old_pid or new_start_ticks <= old_start_ticks:
        raise RuntimeError("role-agent controlled restart did not advance process identity")
    return before


def stop_disable_role_agent():
    checked(["/usr/bin/systemctl", "stop", ROLE_AGENT_UNIT])
    if unit_state("is-active") != "inactive":
        raise RuntimeError("role-agent remained active after maintenance stop")
    checked(["/usr/bin/systemctl", "disable", ROLE_AGENT_UNIT])
    if unit_state("is-enabled") != "disabled":
        raise RuntimeError("role-agent remained enabled after maintenance disable")
    checked(["/usr/bin/systemctl", "reset-failed", ROLE_AGENT_UNIT])
'''
