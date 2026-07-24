"""Isolated source body for the pinned PITR role-agent remote executor."""

from __future__ import annotations


REMOTE_ROLE_AGENT_EXECUTOR_BODY = r'''
import json
import sys
import types

ROLE_AGENT_UNIT = "mvn-patroni-role-agent.service"
ROLE_AGENT_PATH = "/usr/local/sbin/mvn-patroni-role-agent"
ROLE_IDENTITY_PATH = "/usr/local/sbin/patroni_local_identity.py"
ROLE_UNIT_PATH = "/etc/systemd/system/mvn-patroni-role-agent.service"
ROLE_ENV_PATH = "/etc/default/mvn-patroni-role-agent"
OPERATION_GUARD_PATH = "/usr/local/sbin/mvn_postgres_pitr_operation_guard.py"
OPERATION_CLEANUP_PATH = "/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py"
MAINTENANCE_MARKER = "/run/mvn-postgres-pitr-maintenance"
RELEASE_MANIFEST = "/var/lib/mvn-postgres-pitr/release-manifest.json"
GLOBAL_LOCK = "/run/lock/mvn-postgres-pitr-prerequisites.lock"
ROLE_ASSET_MODES = {
    ROLE_AGENT_PATH: 0o755,
    ROLE_IDENTITY_PATH: 0o644,
    ROLE_UNIT_PATH: 0o644,
    OPERATION_GUARD_PATH: 0o755,
    OPERATION_CLEANUP_PATH: 0o755,
}
NODE_CONTRACTS = {
    "/opt/air-api": "mvn-api",
    "/opt/mvn-reserve": "zakup",
}
CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "DOCKER_CONTEXT": "default",
}


def fail(message, status=70):
    print(f"pitr role-agent executor: {message}", file=sys.stderr)
    return status


def read_root_file(path, *, mode, maximum=2097152):
    metadata = os.lstat(path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise RuntimeError(f"role-agent file metadata is unsafe: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        fields = (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns",
        )
        if tuple(getattr(opened, name) for name in fields) != tuple(
            getattr(metadata, name) for name in fields
        ):
            raise RuntimeError(f"role-agent file changed while opening: {path}")
        chunks = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(131072, maximum + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                raise RuntimeError(f"role-agent file exceeds its size bound: {path}")
            chunks.append(chunk)
        finished = os.fstat(descriptor)
        if tuple(getattr(finished, name) for name in fields) != tuple(
            getattr(opened, name) for name in fields
        ):
            raise RuntimeError(f"role-agent file changed while reading: {path}")
        return b"".join(chunks), finished
    finally:
        os.close(descriptor)


def attest_manifest(raw_manifest):
    try:
        manifest = json.loads(raw_manifest)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("role-agent asset manifest is invalid") from exc
    if not isinstance(manifest, dict) or set(manifest) != set(ROLE_ASSET_MODES):
        raise RuntimeError("role-agent asset manifest has an unexpected path set")
    sources = {}
    for path, mode in ROLE_ASSET_MODES.items():
        digest = manifest.get(path)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"role-agent digest is invalid: {path}")
        content, _ = read_root_file(path, mode=mode)
        if hashlib.sha256(content).hexdigest() != digest:
            raise RuntimeError(f"role-agent digest mismatch: {path}")
        sources[path] = content
    return manifest, sources


def expected_role_environment(project_dir):
    node = NODE_CONTRACTS.get(project_dir)
    if node is None:
        raise RuntimeError("unreviewed role-agent project directory")
    return {
        "HA_PROJECT_DIR": project_dir,
        "HA_COMPOSE_FILE": "docker-compose.patroni.yml",
        "HA_PATRONI_URL": "http://127.0.0.1:8008/patroni",
        "HA_PATRONI_SCOPE": "mvn-postgres",
        "HA_PATRONI_NAME": node,
        "HA_PATRONI_MAX_DCS_AGE_SECONDS": "20",
        "HA_READY_URL": "http://127.0.0.1:18080/api/ready",
        "HA_APP_SERVICE": "",
        "HA_PRIMARY_SYSTEMD_UNITS": (
            "mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer"
        ),
        "HA_ROLE_POLL_SECONDS": "3",
        "HA_PROMOTION_DELAY_SECONDS": "8",
        "HA_READY_ATTEMPTS": "30",
    }


def attest_role_environment(project_dir):
    content, _ = read_root_file(ROLE_ENV_PATH, mode=0o600, maximum=16384)
    actual = {}
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError("role-agent environment is not UTF-8") from exc
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError("role-agent environment contains an invalid line")
        name, value = line.split("=", 1)
        if name in actual:
            raise RuntimeError("role-agent environment contains a duplicate key")
        actual[name] = value
    expected = expected_role_environment(project_dir)
    if actual != expected:
        raise RuntimeError("role-agent environment differs from the reviewed node contract")
    return expected


def run_command(args, *, environment=CLEAN_ENV, timeout=60):
    return subprocess.run(
        list(args),
        env=environment,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def checked(args, *, environment=CLEAN_ENV, timeout=60):
    result = run_command(args, environment=environment, timeout=timeout)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or "command failed: " + " ".join(args))
    return result.stdout.strip()


def unit_state(kind):
    result = run_command(["/usr/bin/systemctl", kind, ROLE_AGENT_UNIT])
    value = result.stdout.strip()
    allowed = {
        "is-active": {(0, "active"), (3, "inactive")},
        "is-enabled": {(0, "enabled"), (1, "disabled")},
    }
    if (result.returncode, value) not in allowed[kind]:
        raise RuntimeError(
            f"role-agent {kind} state is not exact: "
            f"rc={result.returncode} value={value}"
        )
    return value


def attest_loaded_unit():
    properties = {
        "FragmentPath": ROLE_UNIT_PATH,
        "DropInPaths": "",
        "NeedDaemonReload": "no",
        "Restart": "always",
    }
    for name, expected in properties.items():
        actual = checked([
            "/usr/bin/systemctl", "show", f"--property={name}", "--value",
            ROLE_AGENT_UNIT,
        ])
        if actual != expected:
            raise RuntimeError(f"role-agent loaded unit property drifted: {name}")


def marker_value():
    try:
        content, _ = read_root_file(MAINTENANCE_MARKER, mode=0o600, maximum=34)
    except FileNotFoundError:
        return None
    if re.fullmatch(rb"[0-9a-f]{32}\n", content) is None:
        raise RuntimeError("PITR maintenance marker is invalid")
    return content[:-1].decode("ascii")


def finalized_transaction(project_dir, transaction_id):
    content, _ = read_root_file(RELEASE_MANIFEST, mode=0o600)
    try:
        manifest = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("PITR release manifest is invalid") from exc
    canonical = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
        + b"\n"
    )
    expected_modes = dict(EXPECTED_ASSET_MODES)
    expected_modes[os.path.join(project_dir, "docker-compose.patroni.yml")] = 0o644
    if (
        content != canonical
        or not isinstance(manifest, dict)
        or set(manifest) != {"files", "project_dir", "release_sha256", "txid", "version"}
        or type(manifest.get("version")) is not int
        or manifest.get("version") != 1
        or manifest.get("project_dir") != project_dir
        or manifest.get("txid") != transaction_id
        or not re.fullmatch(r"[0-9a-f]{64}", manifest.get("release_sha256", ""))
        or not isinstance(manifest.get("files"), list)
    ):
        raise RuntimeError("PITR release manifest does not prove this transaction")
    paths = []
    for item in manifest["files"]:
        path = item.get("path") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or set(item) != {"mode", "path", "sha256"}
            or path not in expected_modes
            or item.get("mode") != expected_modes[path]
            or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", ""))
        ):
            raise RuntimeError("PITR release manifest contains an invalid asset")
        body, _ = read_root_file(path, mode=item["mode"], maximum=1048576)
        if hashlib.sha256(body).hexdigest() != item["sha256"]:
            raise RuntimeError(f"finalized PITR release asset drifted: {path}")
        paths.append(path)
    if paths != sorted(expected_modes):
        raise RuntimeError("PITR release manifest asset set is incomplete")


def require_fence(project_dir, transaction_id, *, allow_finalized):
    current = marker_value()
    if current == transaction_id:
        return "maintenance"
    if current is not None:
        raise RuntimeError("another transaction owns the PITR maintenance marker")
    if not allow_finalized:
        raise RuntimeError("PITR maintenance marker is absent")
    finalized_transaction(project_dir, transaction_id)
    return "finalized"


def execute_attested_module(name, path, source):
    module = types.ModuleType(name)
    module.__file__ = path
    module.__package__ = name.rpartition(".")[0]
    sys.modules[name] = module
    exec(compile(source, path, "exec"), module.__dict__)
    return module


def load_attested_modules(sources, expected_environment):
    scripts_module = types.ModuleType("scripts")
    scripts_module.__path__ = []
    ha_module = types.ModuleType("scripts.ha")
    ha_module.__path__ = []
    sys.modules["scripts"] = scripts_module
    sys.modules["scripts.ha"] = ha_module
    cleanup = execute_attested_module(
        "scripts.ha.pitr_operation_cleanup",
        OPERATION_CLEANUP_PATH,
        sources[OPERATION_CLEANUP_PATH],
    )
    guard = execute_attested_module(
        "scripts.ha.pitr_operation_guard",
        OPERATION_GUARD_PATH,
        sources[OPERATION_GUARD_PATH],
    )
    identity = execute_attested_module(
        "scripts.ha.patroni_local_identity",
        ROLE_IDENTITY_PATH,
        sources[ROLE_IDENTITY_PATH],
    )
    sys.modules["patroni_local_identity"] = identity
    role_agent = execute_attested_module(
        "mvn_pinned_patroni_role_agent",
        ROLE_AGENT_PATH,
        sources[ROLE_AGENT_PATH],
    )
    os.environ.clear()
    os.environ.update(CLEAN_ENV)
    os.environ.update(expected_environment)
    config = role_agent.load_config()
    return guard, role_agent, config


def attest_contract(raw_manifest, project_dir):
    manifest, sources = attest_manifest(raw_manifest)
    expected_environment = attest_role_environment(project_dir)
    attest_loaded_unit()
    guard, role_agent, config = load_attested_modules(
        sources, expected_environment
    )
    return manifest, expected_environment, guard, role_agent, config


def drain_operations(project_dir, transaction_id, guard, *, wait_seconds=10):
    deadline = time.monotonic() + wait_seconds
    while guard.list_records(project_dir=project_dir) and time.monotonic() < deadline:
        time.sleep(0.25)
    records = guard.list_records(project_dir=project_dir)
    foreign = [
        record.operation_id
        for record in records
        if record.operation_id != transaction_id
    ]
    if foreign:
        raise RuntimeError(
            "foreign PITR operation records remain; refusing cancellation: "
            + ",".join(foreign)
        )
    if not records:
        return
    try:
        guard.reconcile_project_operations(project_dir)
    except RuntimeError:
        guard.cancel_all_project_operations(project_dir)
        guard.reconcile_project_operations(project_dir)
    if guard.list_records(project_dir=project_dir):
        raise RuntimeError("PITR operation records remained after bounded cleanup")


def open_global_lock():
    descriptor = os.open(
        GLOBAL_LOCK,
        os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or metadata.st_nlink != 1
    ):
        os.close(descriptor)
        raise RuntimeError("shared PITR lock metadata is unsafe")
    os.fchmod(descriptor, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise RuntimeError("another PITR operation is active") from exc
    return descriptor


def open_deploy_lock_bounded(project_dir, *, wait_seconds=30):
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return open_deploy_lock(project_dir)
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise RuntimeError("project deployment lock remained busy")
            time.sleep(0.25)


def read_project_state(path, expected):
    content, _ = read_root_file(str(path), mode=0o600, maximum=16384)
    if content != expected:
        raise RuntimeError(f"role-agent state is not safely converged: {path}")


def readiness_state():
    result = run_command([
        "/usr/bin/curl", "-sS", "--max-time", "5", "-w", "\n%{http_code}",
        "http://127.0.0.1:18080/api/ready",
    ])
    if result.returncode != 0:
        raise RuntimeError("local API readiness proof failed")
    lines = result.stdout.rstrip().splitlines()
    if len(lines) < 2 or not lines[-1].isdigit():
        raise RuntimeError("local API readiness response is invalid")
    try:
        payload = json.loads("\n".join(lines[:-1]))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("local API readiness JSON is invalid") from exc
    return int(lines[-1]), payload


def prove_safe_state(role_agent, config, *, required, expected_role=None):
    if required == "fenced":
        role = "standby"
        state = b"fencing\n"
    else:
        role = role_agent._fetch_configured_patroni_role(config)
        if required == "standby" and role != "standby":
            raise RuntimeError("node is no longer the proved standby")
        if required == "live" and role != expected_role:
            raise RuntimeError(
                f"local Patroni role proof differs: expected={expected_role} actual={role}"
            )
        state = (role + "\n").encode("ascii")
    expected_app = role_agent.role_env(role, bot_process=False).encode("ascii")
    expected_bot = role_agent.role_env(
        role, bot_process=True, bot_enabled=False
    ).encode("ascii")
    read_project_state(config.state_file, state)
    read_project_state(config.app_role_env, expected_app)
    read_project_state(config.bot_role_env, expected_bot)
    running = role_agent._running_services(config)
    apps = running.intersection(set(role_agent.APP_SERVICE_NAMES))
    if required == "fenced":
        if apps or "bot" in running:
            raise RuntimeError("fenced runtime still owns app or bot")
    else:
        if len(apps) != 1 or "bot" in running:
            raise RuntimeError("role-agent API ownership or legacy bot fencing did not converge")
        status, payload = readiness_state()
        expected_status = 200 if role == "primary" else 503
        expected_traffic = "enabled" if role == "primary" else "disabled"
        if status != expected_status or payload.get("traffic") != expected_traffic:
            raise RuntimeError("API readiness does not match Patroni ownership")
    timer_role = "standby" if marker_value() is not None else role
    if not role_agent._systemd_units_match(config, timer_role):
        raise RuntimeError("PITR timer ownership did not converge")
    return role


def quiesce(phase, project_dir, transaction_id, raw_manifest):
    manifest, expected, guard, role_agent, config = attest_contract(
        raw_manifest, project_dir
    )
    require_fence(project_dir, transaction_id, allow_finalized=False)
    drain_operations(project_dir, transaction_id, guard)
    global_fd = open_global_lock()
    deploy_fd = None
    try:
        deploy_fd = open_deploy_lock_bounded(project_dir)
        manifest, expected, guard, role_agent, config = attest_contract(
            raw_manifest, project_dir
        )
        drain_operations(
            project_dir, transaction_id, guard, wait_seconds=0
        )
        require_fence(project_dir, transaction_id, allow_finalized=False)
        active_state = unit_state("is-active")
        enabled_state = unit_state("is-enabled")
        if active_state == "active":
            # Prove the pre-restart state safe first.  While the project lock
            # is held, the agent cannot activate runtime owners; the exact
            # maintenance marker also keeps primary-only PITR timers stopped.
            if phase == "quiesce-fenced":
                role_agent._fence_lost_primary(config)
                prove_safe_state(role_agent, config, required="fenced")
            else:
                prove_safe_state(role_agent, config, required="standby")
            # Do not compare wall-clock file timestamps with coarse kernel
            # boot time.  A controlled restart instead proves that systemd
            # loaded the unchanged, attested generation by a strictly newer
            # clock-free /proc start-tick identity.
            refresh_live_process(
                expected,
                manifest,
                expected_enabled=enabled_state,
            )
            require_fence(project_dir, transaction_id, allow_finalized=False)
        if phase == "quiesce-fenced":
            role_agent._fence_lost_primary(config)
            prove_safe_state(role_agent, config, required="fenced")
        else:
            prove_safe_state(role_agent, config, required="standby")
        stop_disable_role_agent()
        required = "fenced" if phase == "quiesce-fenced" else "standby"
        prove_safe_state(role_agent, config, required=required)
        require_fence(project_dir, transaction_id, allow_finalized=False)
    finally:
        if deploy_fd is not None:
            os.close(deploy_fd)
        os.close(global_fd)


def wait_for_convergence(role_agent, config, expected_role, *, timeout=90):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            return prove_safe_state(
                role_agent,
                config,
                required="live",
                expected_role=expected_role,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            last = exc
            time.sleep(1)
    raise RuntimeError(f"role-agent did not converge within the bound: {last}")


def resume(project_dir, transaction_id, raw_manifest, expected_role):
    manifest, expected, guard, role_agent, config = attest_contract(
        raw_manifest, project_dir
    )
    initial_fence_state = require_fence(
        project_dir, transaction_id, allow_finalized=True
    )
    drain_operations(project_dir, transaction_id, guard)
    global_fd = open_global_lock()
    deploy_fd = None
    final_deploy_fd = None
    try:
        deploy_fd = open_deploy_lock_bounded(project_dir)
        manifest, expected, guard, role_agent, config = attest_contract(
            raw_manifest, project_dir
        )
        drain_operations(
            project_dir, transaction_id, guard, wait_seconds=0
        )
        fence_state = require_fence(
            project_dir, transaction_id, allow_finalized=True
        )
        if fence_state != initial_fence_state:
            raise RuntimeError("PITR fence state changed before role-agent resume")
        active_state = unit_state("is-active")
        enabled_state = unit_state("is-enabled")
        if (active_state, enabled_state) in {
            ("active", "disabled"),
            ("inactive", "enabled"),
        }:
            # These are owned crash boundaries from stop/disable or
            # enable/start.  Converge them to the sole restartable baseline
            # without trusting which mutation returned to the controller.
            role_agent._fence_lost_primary(config)
            prove_safe_state(role_agent, config, required="fenced")
            if active_state == "active":
                refresh_live_process(
                    expected,
                    manifest,
                    expected_enabled=enabled_state,
                )
            if require_fence(
                project_dir,
                transaction_id,
                allow_finalized=True,
            ) != fence_state:
                raise RuntimeError(
                    "PITR fence state changed during mixed-state recovery"
                )
            stop_disable_role_agent()
            if require_fence(
                project_dir,
                transaction_id,
                allow_finalized=True,
            ) != fence_state:
                raise RuntimeError(
                    "PITR fence state changed after mixed-state recovery"
                )
            active_state = "inactive"
            enabled_state = "disabled"
        if (active_state, enabled_state) == ("inactive", "disabled"):
            generation = snapshot_role_generation(manifest)
            checked(["/usr/bin/systemctl", "enable", ROLE_AGENT_UNIT])
            checked(["/usr/bin/systemctl", "start", ROLE_AGENT_UNIT])
            prove_live_generation(
                expected,
                manifest,
                generation,
                "maintenance resume",
            )
        elif (active_state, enabled_state) == ("active", "enabled"):
            prove_safe_state(
                role_agent,
                config,
                required="live",
                expected_role=expected_role,
            )
            generation = refresh_live_process(expected, manifest)
            if require_fence(
                project_dir,
                transaction_id,
                allow_finalized=True,
            ) != fence_state:
                raise RuntimeError("PITR fence state changed during role-agent refresh")
            prove_safe_state(
                role_agent,
                config,
                required="live",
                expected_role=expected_role,
            )
        else:
            raise RuntimeError("role-agent systemd state is not replay-convergent")
        os.close(deploy_fd)
        deploy_fd = None
        wait_for_convergence(role_agent, config, expected_role)
        final_deploy_fd = open_deploy_lock_bounded(project_dir)
        manifest, expected, guard, role_agent, config = attest_contract(
            raw_manifest, project_dir
        )
        prove_live_generation(
            expected,
            manifest,
            generation,
            "maintenance resume convergence",
        )
        prove_safe_state(
            role_agent,
            config,
            required="live",
            expected_role=expected_role,
        )
        require_fence(
            project_dir,
            transaction_id,
            allow_finalized=fence_state == "finalized",
        )
    finally:
        if final_deploy_fd is not None:
            os.close(final_deploy_fd)
        if deploy_fd is not None:
            os.close(deploy_fd)
        os.close(global_fd)


def main():
    if len(sys.argv) != 5:
        return fail("invalid invocation", 64)
    if os.geteuid() != 0:
        return fail("root execution is required", 77)
    phase, project_dir, transaction_id, raw_manifest = sys.argv[1:]
    if phase not in {
        "quiesce-fenced",
        "quiesce-standby",
        "resume-primary",
        "resume-standby",
    }:
        return fail("unsupported role-agent phase", 64)
    if project_dir not in NODE_CONTRACTS:
        return fail("unreviewed role-agent project directory", 64)
    if re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None:
        return fail("invalid PITR transaction ID", 64)
    try:
        if phase.startswith("quiesce-"):
            quiesce(phase, project_dir, transaction_id, raw_manifest)
        else:
            resume(
                project_dir,
                transaction_id,
                raw_manifest,
                phase.removeprefix("resume-"),
            )
    except (OSError, RuntimeError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        return fail(str(exc))
    print(f"role_agent_phase={phase} status=proved")
    return 0


raise SystemExit(main())
'''
