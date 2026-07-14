"""Runtime-ownership proof embedded into the Patroni rollout executor."""

REMOTE_RUNTIME_PROOF = r'''
def read_proc_file(path, maximum=131072):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != ROOT:
            die("role-agent process metadata is unsafe")
        data = os.read(fd, maximum + 1)
        if len(data) > maximum or os.read(fd, 1):
            die("role-agent process metadata exceeds limit")
        return data
    finally:
        os.close(fd)

def process_start_ns(pid):
    raw = read_proc_file("/proc/" + pid + "/stat", 8192).decode("ascii")
    boundary = raw.rfind(") ")
    fields = raw[boundary + 2:].split() if boundary > 0 else []
    if len(fields) <= 19 or not fields[19].isdigit():
        die("role-agent process start metadata is invalid")
    boot = []
    for line in read_proc_file("/proc/stat", 1048576).decode("ascii").splitlines():
        if line.startswith("btime "):
            boot.append(line.split())
    if len(boot) != 1 or len(boot[0]) != 2 or not boot[0][1].isdigit():
        die("kernel boot-time metadata is invalid")
    ticks = os.sysconf("SC_CLK_TCK")
    if not isinstance(ticks, int) or ticks <= 0:
        die("kernel clock-tick metadata is invalid")
    return ((int(boot[0][1]) * ticks + int(fields[19])) * 1000000000) // ticks

def validate_role_process_generation(pid, expected):
    assets = (
        "/usr/local/sbin/mvn-patroni-role-agent",
        "/usr/local/sbin/patroni_local_identity.py",
        "/etc/systemd/system/mvn-patroni-role-agent.service",
        "/etc/default/mvn-patroni-role-agent",
    )
    newest_asset = max(os.lstat(path).st_ctime_ns for path in assets)
    if process_start_ns(pid) < newest_asset:
        die("live role-agent predates the reviewed on-disk generation")
    live = {}
    for entry in read_proc_file("/proc/" + pid + "/environ").split(b"\0"):
        if not entry:
            continue
        try:
            name, value = entry.decode("utf-8").split("=", 1)
        except (UnicodeDecodeError, ValueError):
            die("role-agent live environment is invalid")
        if name.startswith("HA_"):
            if name in live:
                die("role-agent live environment contains a duplicate key")
            live[name] = value
    if live != expected:
        die("live role-agent environment differs from the reviewed node contract")

def validate_role_agent_runtime(project, node):
    expected = {
        "HA_PROJECT_DIR": project, "HA_COMPOSE_FILE": "docker-compose.patroni.yml",
        "HA_PATRONI_URL": "http://127.0.0.1:8008/patroni",
        "HA_PATRONI_SCOPE": "mvn-postgres", "HA_PATRONI_NAME": node,
        "HA_PATRONI_MAX_DCS_AGE_SECONDS": "20",
        "HA_READY_URL": "http://127.0.0.1:18080/api/ready", "HA_APP_SERVICE": "",
        "HA_PRIMARY_SYSTEMD_UNITS": "mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer",
        "HA_ROLE_POLL_SECONDS": "3", "HA_PROMOTION_DELAY_SECONDS": "8",
        "HA_READY_ATTEMPTS": "30",
    }
    content = read_root_file("/etc/default/mvn-patroni-role-agent").decode("utf-8")
    actual = {}
    for line in content.splitlines():
        if line and not line.startswith("#"):
            if "=" not in line: die("role-agent environment contains an invalid line")
            key, value = line.split("=", 1)
            if key in actual: die("role-agent environment contains a duplicate key")
            actual[key] = value
    if actual != expected:
        die("role-agent environment differs from the reviewed node contract")
    unit = "mvn-patroni-role-agent.service"
    if run(["systemctl", "show", "--property=FragmentPath", "--value", unit]) != \
            "/etc/systemd/system/mvn-patroni-role-agent.service":
        die("role-agent loaded fragment path is unreviewed")
    if run(["systemctl", "show", "--property=DropInPaths", "--value", unit]):
        die("role-agent systemd drop-ins are not allowed")
    if run(["systemctl", "show", "--property=NeedDaemonReload", "--value", unit]) != "no":
        die("role-agent unit is not the loaded on-disk generation")
    if run(["systemctl", "show", "--property=Restart", "--value", unit]) != "always":
        die("role-agent restart policy drifted")
    pid = run(["systemctl", "show", "--property=MainPID", "--value", unit])
    if not re.fullmatch(r"[1-9][0-9]*", pid): die("role-agent MainPID is invalid")
    validate_role_process_generation(pid, expected)
    cmdline = read_proc_file("/proc/" + pid + "/cmdline", 4096)
    if cmdline != b"/usr/bin/python3\0/usr/local/sbin/mvn-patroni-role-agent\0":
        die("live role-agent command line is unreviewed")
    if run(["systemctl", "show", "--property=MainPID", "--value", unit]) != pid:
        die("role-agent MainPID changed during attestation")

def canonical_role_env(role, bot_process):
    primary = role == "primary"
    values = {}
    values["APP_ROLE"] = role
    values["API_READY_ENABLED"] = "false" if bot_process else str(primary).lower()
    values["BOT_ENABLED"] = str(primary and bot_process).lower()
    values["DB_BOOTSTRAP_ENABLED"] = "false"
    values["SCHEDULER_ENABLED"] = str(primary and not bot_process).lower()
    if not primary:
        values.update({"MAIL_IMAP_AUTO_IMPORT_ENABLED": "false",
            "MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED": "false",
            "CLOUDFLARE_PURGE_ENABLED": "false", "CLOUDFLARE_PURGE_DRY_RUN": "true"})
    content = "".join(name + "=" + value + "\n" for name, value in values.items())
    return content, values

def exact_role_env(path, role, bot_process):
    expected_content, expected_values = canonical_role_env(role, bot_process)
    if read_root_file(path) != expected_content.encode("ascii"):
        die("role environment file is not the exact canonical generation: " + path)
    return expected_values

def attest_container_role_environment(project, compose, service, expected):
    identifiers = run(compose_args(project, compose) + ["ps", "-q", service]).splitlines()
    if len(identifiers) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", identifiers[0]):
        die("role-owned service must resolve to exactly one container: " + service)
    inspected = json.loads(run(["docker", "inspect", identifiers[0]]))
    if (not isinstance(inspected, list) or len(inspected) != 1
            or inspected[0].get("State", {}).get("Running") is not True):
        die("role-owned service container is not running: " + service)
    entries = inspected[0].get("Config", {}).get("Env")
    if not isinstance(entries, list) or any(not isinstance(item, str) for item in entries):
        die("role-owned service environment is invalid: " + service)
    for name, value in expected.items():
        matches = [item.split("=", 1)[1] for item in entries if item.startswith(name + "=")]
        if matches != [value]:
            die("live container role environment differs: " + service + ":" + name)

def runtime_ownership_once(project, compose, expected_role):
    if expected_role not in {"primary", "standby"} or local_patroni_role() != expected_role:
        die("runtime ownership expected role does not match Patroni")
    role = read_root_file(project + "/.ha-runtime-role").decode("ascii").strip()
    if role != expected_role: die("role-agent applied state is stale")
    primary = expected_role == "primary"
    expected_app = exact_role_env(project + "/.ha-app-role.env", expected_role, False)
    expected_bot = exact_role_env(project + "/.ha-bot-role.env", expected_role, True)
    services = set(run(compose_args(project, compose) + ["--profile", "bluegreen", "ps",
        "--status", "running", "--services"]).splitlines())
    if len(services.intersection({"app", "app-blue", "app-green"})) != 1:
        die("exactly one API service must be running")
    if ("bot" in services) != primary: die("bot singleton ownership is incorrect")
    app_service = next(iter(services.intersection({"app", "app-blue", "app-green"})))
    attest_container_role_environment(project, compose, app_service, expected_app)
    if primary:
        attest_container_role_environment(project, compose, "bot", expected_bot)
    response = run(["curl", "-sS", "--max-time", "5", "-w", "\n%{http_code}",
        "http://127.0.0.1:18080/api/ready"])
    lines = response.rstrip().splitlines()
    if len(lines) < 2 or not lines[-1].isdigit(): die("API readiness response is invalid")
    payload = json.loads("\n".join(lines[:-1])); status = int(lines[-1])
    expected_status = 200 if primary else 503
    expected_api = "ready" if primary else "not_ready"
    expected_traffic = "enabled" if primary else "disabled"
    if (status != expected_status or payload.get("api") != expected_api
            or payload.get("traffic") != expected_traffic):
        die("API readiness/fencing does not match Patroni ownership")
    scheduler = payload.get("scheduler_runtime")
    if not isinstance(scheduler, dict): die("scheduler runtime proof is missing")
    if primary and (scheduler.get("expected") is not True or scheduler.get("status") != "running"):
        die("primary scheduler is not running")
    if not primary and (scheduler.get("expected") is not False
            or scheduler.get("status") not in {"disabled", "stopped"}):
        die("standby scheduler is not fenced")
    validate_units()

def attest_runtime_ownership(project, compose, expected_role):
    deadline = time.monotonic() + 60
    last = None
    while time.monotonic() < deadline:
        try:
            runtime_ownership_once(project, compose, expected_role); return
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            last = exc; time.sleep(2)
    die("role-agent ownership did not converge: " + str(last))

def prove_final_generation(project, compose, compose_project, volume, payload, journal, node):
    require_completed(journal, "record:final-proved")
    validate_compose(project, compose, compose_project, volume,
                     payload["target_image"], payload["compose_contract_sha256"], payload)
    runtime_attestation(project, compose, payload["target_image"], payload["helper_sha256"])
    final_role = "standby" if node == journal["baseline_primary"] else "primary"
    if final_role == "primary": prove_etcd(payload)
    check_target_dcs(project, compose, journal if final_role == "primary" else None)
    attest_archive_runtime(project, compose, payload["target_image"], payload["helper_sha256"])
    attest_runtime_ownership(project, compose, final_role)

def prove_aborted_generation(project, compose, compose_project, volume, payload):
    validate_compose(project, compose, compose_project, volume,
                     payload["current_image"], payload["compose_contract_sha256"], payload)
    runtime_attestation(project, compose, payload["current_image"])
    check_legacy_dcs(project, compose, payload["legacy_command_sha256"])
'''
