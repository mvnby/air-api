"""Self-contained root executor used by the pinned Patroni rollout controller."""

from __future__ import annotations

try:
    from scripts.ha.patroni_rollout_remote_contract import REMOTE_CONTRACT
    from scripts.ha.patroni_rollout_remote_prelude import REMOTE_PRELUDE
    from scripts.ha.patroni_rollout_remote_runtime import REMOTE_RUNTIME_PROOF
except ModuleNotFoundError:
    from patroni_rollout_remote_contract import REMOTE_CONTRACT  # type: ignore[no-redef]
    from patroni_rollout_remote_prelude import REMOTE_PRELUDE  # type: ignore[no-redef]
    from patroni_rollout_remote_runtime import REMOTE_RUNTIME_PROOF  # type: ignore[no-redef]

REMOTE_EXECUTOR = REMOTE_PRELUDE + REMOTE_CONTRACT + REMOTE_RUNTIME_PROOF + r'''

def validate_role_assets(payload):
    assets = (("/usr/local/sbin/mvn-patroni-role-agent", 0o755, payload["role_agent_sha256"]),
        ("/usr/local/sbin/patroni_local_identity.py", 0o644, payload["role_identity_sha256"]),
        ("/etc/systemd/system/mvn-patroni-role-agent.service", 0o644,
         payload["role_unit_sha256"]))
    for path, mode, digest in assets:
        if sha(read_root_file(path, mode=mode)) != digest:
            die("deployed Patroni role asset digest drifted: " + path)

def local_patroni_role():
    raw = run(["curl", "-fsS", "--max-time", "5", "http://127.0.0.1:8008/patroni"])
    payload = json.loads(raw)
    if payload.get("state") != "running":
        die("local Patroni is not running")
    role = str(payload.get("role", "")).lower()
    if role in {"replica", "standby", "sync_standby", "synchronous_standby"}: return "standby"
    if role in {"leader", "master", "primary"}: return "primary"
    die("local Patroni role is unsupported")

def require_standby(project, compose, expected_primary, allow_unavailable=False):
    try:
        if local_patroni_role() == "standby": return
    except (RuntimeError, ValueError):
        if not allow_unavailable: raise
    peer = {"mvn-api": "10.77.0.2", "zakup": "10.77.0.1"}[expected_primary]
    run(["curl", "-fsS", "--max-time", "5", "http://" + peer + ":8008/leader"])
    recovery = sql(project, compose, "select pg_is_in_recovery();").strip()
    if recovery != "t":
        die("refusing to recreate a node without exact PostgreSQL standby proof")

def prove_etcd(payload):
    source = base64.b64decode(payload["etcd_check_b64"], validate=True).decode("utf-8")
    output = run(["/bin/bash", "-s"], stdin=source)
    passed = [line for line in output.splitlines() if line.startswith("etcd_quorum_status=passed ")]
    if (len(passed) != 1 or "members=3 " not in passed[0]
            or not re.search(r" raft_lag=[0-9]+ ", passed[0])
            or "[etcd-quorum][done] all 3 members are healthy" not in output):
        die("exact bundled etcd quorum proof failed")

def validate_archive(project):
    archive = project + "/postgres-wal-archive"
    meta = os.lstat(archive)
    if (not stat.S_ISDIR(meta.st_mode) or stat.S_ISLNK(meta.st_mode)
            or meta.st_uid != 70 or meta.st_gid != 70
            or stat.S_IMODE(meta.st_mode) != 0o700):
        die("WAL archive directory metadata is unsafe")
    for name in os.listdir(archive):
        if name == ".mvn-pitr-archive.lock":
            lock = os.lstat(archive + "/" + name)
            if (not stat.S_ISREG(lock.st_mode) or stat.S_ISLNK(lock.st_mode)
                    or lock.st_uid != 70 or lock.st_gid != 70
                    or stat.S_IMODE(lock.st_mode) != 0o600 or lock.st_nlink != 1):
                die("WAL archive lock metadata is unsafe")
            continue
        if not (WAL_RE.fullmatch(name) or HISTORY_RE.fullmatch(name)):
            die("WAL archive contains a non-canonical name: " + name)
        path = archive + "/" + name
        entry = os.lstat(path)
        if (not stat.S_ISREG(entry.st_mode) or stat.S_ISLNK(entry.st_mode)
                or entry.st_uid != 70 or entry.st_gid != 70
                or stat.S_IMODE(entry.st_mode) != 0o600 or entry.st_nlink != 1
                or entry.st_size <= 0):
            die("WAL archive entry metadata is unsafe: " + name)
        if (name.endswith(".partial") and entry.st_size != WAL_SIZE):
            die("partial WAL must be exactly one WAL segment: " + name)
        if re.fullmatch(r"[0-9A-F]{24}", name) and entry.st_size != WAL_SIZE:
            die("WAL must be exactly one WAL segment: " + name)

def env_image(project):
    content = read_root_file(project + "/.env").decode("utf-8")
    values = [line.split("=", 1)[1] for line in content.splitlines() if line.startswith("PATRONI_IMAGE=")]
    if len(values) != 1 or not IMAGE_RE.fullmatch(values[0]):
        die(".env must contain one immutable PATRONI_IMAGE")
    return values[0], content

def set_env_image(project, expected, target):
    actual, content = env_image(project)
    if actual == target:
        return
    if actual != expected:
        die("PATRONI_IMAGE generation drifted")
    lines = content.splitlines()
    rewritten = "\n".join("PATRONI_IMAGE=" + target if line.startswith("PATRONI_IMAGE=") else line for line in lines) + "\n"
    atomic(project + "/.env", rewritten.encode())

def image_attestation(image, helper_digest=None):
    inspected = json.loads(run(["docker", "image", "inspect", image]))
    if len(inspected) != 1 or image not in inspected[0].get("RepoDigests", []):
        die("staged image RepoDigest mismatch")
    if inspected[0].get("Architecture") != "amd64":
        die("Patroni image architecture is not amd64")
    sandbox = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL"]
    version = run(sandbox + ["--entrypoint", "patroni", image, "--version"])
    if not version.endswith(" 4.1.4"):
        die("Patroni image version mismatch")
    if helper_digest is None:
        return
    probe = ("import hashlib,json,os,stat; p='" + HELPER_PATH + "'; s=os.lstat(p); "
        "assert stat.S_ISREG(s.st_mode) and not stat.S_ISLNK(s.st_mode) and s.st_uid==0 and s.st_gid==0 "
        "and stat.S_IMODE(s.st_mode)==0o755 and s.st_nlink==1; "
        "print(hashlib.sha256(open(p,'rb').read()).hexdigest())")
    helper = run(sandbox + ["--entrypoint", "python3", image, "-c", probe])
    if helper != helper_digest:
        die("Patroni WAL helper digest mismatch")

def container_id(project, compose):
    identifiers = run(compose_args(project, compose) + ["ps", "-q", "db"]).splitlines()
    if len(identifiers) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", identifiers[0]):
        die("Compose must resolve exactly one db container")
    identifier = identifiers[0]
    state = json.loads(run(["docker", "inspect", identifier]))[0].get("State", {})
    if state.get("Running") is not True or state.get("Status") != "running":
        die("db container is not running")
    health = state.get("Health", {}).get("Status")
    if health != "healthy":
        die("db container is not healthy")
    return identifier

def runtime_attestation(project, compose, image, helper_digest=None):
    identifier = container_id(project, compose)
    config_image = run(["docker", "inspect", "--format", "{{.Config.Image}}", identifier])
    if config_image != image:
        die("running db container does not use the exact image reference")
    wanted_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", image])
    runtime_id = run(["docker", "inspect", "--format", "{{.Image}}", identifier])
    if runtime_id != wanted_id:
        die("running db container image ID mismatch")
    version = run(["docker", "exec", identifier, "patroni", "--version"])
    if not version.endswith(" 4.1.4"):
        die("running Patroni version mismatch")
    if helper_digest is not None:
        image_attestation(image, helper_digest)
        probe = ("import hashlib,os,stat; p='" + HELPER_PATH + "'; s=os.lstat(p); "
            "assert stat.S_ISREG(s.st_mode) and not stat.S_ISLNK(s.st_mode) and s.st_uid==0 and s.st_gid==0 "
            "and stat.S_IMODE(s.st_mode)==0o755 and s.st_nlink==1; "
            "print(hashlib.sha256(open(p,'rb').read()).hexdigest())")
        if run(["docker", "exec", identifier, "python3", "-c", probe]) != helper_digest:
            die("running container WAL helper digest mismatch")
    settings = sql(project, compose, "select name, setting from pg_settings where name in ('archive_mode','archive_timeout','archive_command') order by name;")
    if "archive_mode|on" not in settings or "archive_timeout|300" not in settings:
        die("runtime archive mode/timeout drifted")

def attest_archive_runtime(project, compose, image, helper_digest):
    runtime_attestation(project, compose, image, helper_digest)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        command = sql(project, compose, "show archive_command;")
        if command == EXPECTED_COMMAND:
            return
        time.sleep(2)
    die("running PostgreSQL did not reload the reviewed archive_command")

def runtime_generation_matches(project, compose, image):
    try:
        identifier = container_id(project, compose)
    except RuntimeError:
        return False
    config_image = run(["docker", "inspect", "--format", "{{.Config.Image}}", identifier])
    wanted_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", image])
    runtime_id = run(["docker", "inspect", "--format", "{{.Image}}", identifier])
    return config_image == image and runtime_id == wanted_id

def validate_compose(project, compose, compose_project, volume, expected_image, approved_digest, payload):
    os.chdir(project)
    unrendered = run(compose_args(project, compose) + ["config", "--no-env-resolution",
        "--no-interpolate", "--format", "json"])
    try:
        helper = base64.b64decode(payload["contract_helper_b64"], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        die("Compose contract helper is invalid")
    measured = run(["/usr/bin/python3", "-I", "-c", helper], stdin=unrendered)
    if measured != approved_digest:
        die("complete un-interpolated Compose db contract drifted")
    config = json.loads(run(compose_args(project, compose) + ["config", "--format", "json"]))
    if config.get("name") != compose_project:
        die("Compose project identity drifted")
    db = config.get("services", {}).get("db", {})
    if db.get("image") != expected_image:
        die("resolved Compose db image drifted")
    mounts = [item for item in db.get("volumes", []) if item.get("target") == "/var/lib/postgresql/data"]
    if (len(mounts) != 1 or mounts[0].get("source") != "postgres_data"
            or mounts[0].get("type") != "volume"):
        die("reviewed external PGDATA volume drifted")
    top = config.get("volumes", {}).get("postgres_data", {})
    if top.get("name") != volume or top.get("external") is not True:
        die("PGDATA volume must remain exact and external")
    return measured

def yaml_config(project, compose):
    identifier = container_id(project, compose)
    raw = run(["docker", "exec", identifier, "patronictl", "-c", "/etc/patroni/patroni.yml", "show-config", "mvn-postgres"])
    code = "import json,sys,yaml; print(json.dumps(yaml.safe_load(sys.stdin.read()),sort_keys=True,separators=(',',':')))"
    parsed = run(["docker", "exec", "-i", identifier, "python3", "-c", code], stdin=raw)
    value = json.loads(parsed)
    if not isinstance(value, dict):
        die("Patroni DCS config is invalid")
    return value

def archive_values(config):
    params = config.get("postgresql", {}).get("parameters", {})
    values = {key: str(params.get(key, "")) for key in ("archive_mode", "archive_timeout", "archive_command")}
    return values

def check_legacy_dcs(project, compose, legacy_digest):
    values = archive_values(yaml_config(project, compose))
    if values["archive_mode"] != "on" or values["archive_timeout"] != "300":
        die("legacy DCS archive mode/timeout drifted")
    if values["archive_command"] != LEGACY_COMMAND or sha(values["archive_command"]) != legacy_digest:
        die("legacy DCS archive command digest drifted")

def supported_archive_command(config, legacy_digest):
    values = archive_values(config)
    if values["archive_mode"] != "on" or values["archive_timeout"] != "300":
        die("DCS archive mode/timeout drifted")
    command = values["archive_command"]
    if command != EXPECTED_COMMAND and sha(command) != legacy_digest:
        die("DCS archive command is outside the approved generations")
    return command

def check_supported_dcs(project, compose, legacy_digest):
    return supported_archive_command(yaml_config(project, compose), legacy_digest)

def diff_paths(before, after, prefix=()):
    if isinstance(before, dict) and isinstance(after, dict):
        changed = []
        for key in set(before) | set(after):
            changed.extend(diff_paths(before.get(key), after.get(key), prefix + (key,)))
        return changed
    return [] if before == after else [prefix]

def journal_dcs_baseline(journal):
    baseline = journal.get("dcs_baseline")
    digest = journal.get("dcs_baseline_sha256")
    if (not isinstance(baseline, dict) or not isinstance(digest, str)
            or not DIGEST_RE.fullmatch(digest) or sha(canonical(baseline)) != digest):
        die("journal has no canonical DCS baseline")
    command = journal.get("baseline_archive_command")
    if command not in {LEGACY_COMMAND, EXPECTED_COMMAND}:
        die("journal DCS baseline command is outside the approved generations")
    if archive_values(baseline) != {
            "archive_mode": "on", "archive_timeout": "300",
            "archive_command": command}:
        die("journal DCS baseline differs from the reviewed generation")
    return baseline

def check_baseline_dcs(project, compose, journal):
    if yaml_config(project, compose) != journal_dcs_baseline(journal):
        die("DCS generation drifted from the journaled baseline")

def check_target_dcs(project, compose, journal=None):
    current = yaml_config(project, compose)
    values = archive_values(current)
    if values != {"archive_mode": "on", "archive_timeout": "300",
                  "archive_command": EXPECTED_COMMAND}:
        die("DCS archive settings do not match the reviewed target")
    if journal is not None:
        baseline = journal_dcs_baseline(journal)
        expected_diff = ([] if journal["baseline_archive_command"] == EXPECTED_COMMAND
                         else [("postgresql", "parameters", "archive_command")])
        if diff_paths(baseline, current) != expected_diff:
            die("target DCS generation drifted from the journaled baseline")

def apply_archive_command(project, compose, legacy_digest, journal_path, journal):
    identifier = container_id(project, compose)
    before = yaml_config(project, compose)
    values = archive_values(before)
    baseline = journal_dcs_baseline(journal)
    baseline_command = journal["baseline_archive_command"]
    if values["archive_command"] == EXPECTED_COMMAND:
        expected_diff = ([] if baseline_command == EXPECTED_COMMAND
                         else [("postgresql", "parameters", "archive_command")])
        if (values != {"archive_mode": "on", "archive_timeout": "300",
                       "archive_command": EXPECTED_COMMAND}
                or diff_paths(baseline, before) != expected_diff):
            die("target DCS generation drifted from the journaled baseline")
        return
    if baseline_command != LEGACY_COMMAND:
        die("target DCS baseline cannot transition through the legacy generation")
    if before != baseline:
        die("legacy DCS generation drifted from the journaled baseline")
    check_legacy_dcs(project, compose, legacy_digest)
    run(["docker", "exec", identifier, "patronictl", "-c", "/etc/patroni/patroni.yml",
         "edit-config", "mvn-postgres", "--pg", "archive_command=" + EXPECTED_COMMAND, "--force"])
    after = yaml_config(project, compose)
    changed = diff_paths(baseline, after)
    if changed != [("postgresql", "parameters", "archive_command")]:
        die("DCS mutation changed an unreviewed key: " + repr(changed))
    values = archive_values(after)
    if values != {"archive_mode": "on", "archive_timeout": "300", "archive_command": EXPECTED_COMMAND}:
        die("DCS archive settings do not match the reviewed target")

def revert_archive_command(project, compose, legacy_digest, journal):
    original = journal.get("baseline_archive_command")
    if original not in {LEGACY_COMMAND, EXPECTED_COMMAND}:
        die("journal has no attested baseline archive command")
    if original == LEGACY_COMMAND and sha(original) != legacy_digest:
        die("journal legacy archive command digest drifted")
    identifier = container_id(project, compose)
    baseline = journal_dcs_baseline(journal)
    before = yaml_config(project, compose)
    values = archive_values(before)
    if values["archive_command"] == original:
        if before != baseline:
            die("compensated DCS generation drifted from the journaled baseline")
        if original == LEGACY_COMMAND:
            check_legacy_dcs(project, compose, legacy_digest)
        else:
            check_target_dcs(project, compose, journal)
        return
    if (values != {"archive_mode": "on", "archive_timeout": "300",
                   "archive_command": EXPECTED_COMMAND}
            or diff_paths(baseline, before) != [
                ("postgresql", "parameters", "archive_command")]):
        die("cannot compensate an unreviewed DCS generation")
    run(["docker", "exec", identifier, "patronictl", "-c", "/etc/patroni/patroni.yml",
         "edit-config", "mvn-postgres", "--pg", "archive_command=" + original, "--force"])
    after = yaml_config(project, compose)
    if after != baseline:
        die("compensating DCS mutation did not restore the exact baseline")
    if original == LEGACY_COMMAND:
        check_legacy_dcs(project, compose, legacy_digest)
    else:
        check_target_dcs(project, compose, journal)

def sql(project, compose, statement):
    command = compose_args(project, compose) + ["exec", "-T", "db", "sh", "-lc",
        'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -AtF "|"']
    return run(command, stdin=statement)

def prove_archive(project, compose):
    baseline = sql(project, compose, "select coalesce(last_archived_wal,''), failed_count from pg_stat_archiver;").split("|")
    if len(baseline) != 2 or not baseline[1].isdigit():
        die("pg_stat_archiver baseline is invalid")
    baseline_failures = baseline[1]
    expected = sql(project, compose, "select pg_walfile_name(pg_switch_wal());").strip()
    if not re.fullmatch(r"[0-9A-F]{24}", expected):
        die("forced WAL switch returned an invalid segment")
    archive = project + "/postgres-wal-archive/" + expected
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        stats = sql(project, compose, "select coalesce(last_archived_wal,''), failed_count from pg_stat_archiver;").split("|")
        archived = stats[0] if len(stats) == 2 else ""
        reached = (re.fullmatch(r"[0-9A-F]{24}", archived) is not None
                   and int(archived, 16) >= int(expected, 16))
        if (len(stats) == 2 and reached and stats[1] == baseline_failures
                and os.path.exists(archive)):
            meta = os.lstat(archive)
            if (stat.S_ISREG(meta.st_mode) and not stat.S_ISLNK(meta.st_mode)
                    and meta.st_uid == 70 and meta.st_gid == 70
                    and stat.S_IMODE(meta.st_mode) == 0o600 and meta.st_size == WAL_SIZE):
                return expected
            die("new helper archived WAL with unsafe metadata")
        time.sleep(2)
    die("new helper did not archive the forced WAL segment")

def preflight(project, compose, compose_project, volume, payload, node):
    pitr_fence(payload["maintenance_transaction_id"])
    validate_units()
    validate_role_assets(payload)
    validate_role_agent_runtime(project, node)
    validate_archive(project)
    actual = env_image(project)[0]
    if actual not in {payload["current_image"], payload["target_image"]}:
        die("PATRONI_IMAGE is outside the approved transaction generations")
    validate_compose(project, compose, compose_project, volume, actual,
                     payload["compose_contract_sha256"], payload)
    helper = payload["helper_sha256"] if actual == payload["target_image"] else None
    runtime_attestation(project, compose, actual, helper)
    prove_etcd(payload)
    check_supported_dcs(project, compose, payload["legacy_command_sha256"])

def open_lock():
    flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(LOCK_PATH, flags | os.O_CREAT | os.O_EXCL, 0o600)
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, ROOT, ROOT)
    except FileExistsError:
        before = os.lstat(LOCK_PATH)
        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                or before.st_uid != ROOT or before.st_gid != ROOT
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
            die("rollout lock metadata is unsafe")
        descriptor = os.open(LOCK_PATH, flags)
        opened = os.fstat(descriptor)
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or opened.st_nlink != 1):
            os.close(descriptor)
            die("rollout lock changed while opening")
    return descriptor

def open_project_lock(project):
    path = project + "/.deploy.lock"
    flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, ROOT, ROOT)
    except FileExistsError:
        before = os.lstat(path)
        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                or before.st_uid != ROOT or before.st_gid != ROOT
                or before.st_nlink != 1 or before.st_mode & 0o022):
            die("shared deploy lock metadata is unsafe")
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or opened.st_nlink != 1):
            os.close(descriptor)
            die("shared deploy lock changed while opening")
    return descriptor

def normalize_locked_project_lock(descriptor):
    metadata = os.fstat(descriptor)
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != ROOT
            or metadata.st_gid != ROOT or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) not in {0o600, 0o644}):
        die("locked shared deploy file is unsafe")
    os.fchmod(descriptor, 0o600)
    if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o600:
        die("shared deploy lock mode migration failed")

def main():
    if os.geteuid() != ROOT or len(sys.argv) != 4:
        die("rollout executor requires root and exact arguments")
    action, node, txid = sys.argv[1:]
    raw = sys.stdin.buffer.read(65537)
    if not raw or len(raw) > 65536:
        die("rollout payload size is invalid")
    payload = json.loads(raw)
    validate_payload(payload)
    validate_action(action, payload)
    project, compose, compose_project, volume, txdir, journal_path, marker_path = paths(node, txid)
    safe_dir("/run/lock", 0o755) if not os.path.exists("/run/lock") else None
    lock = open_lock()
    deploy_lock = None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action not in {"journal-status", "status"}:
            deploy_lock = open_project_lock(project)
            fcntl.flock(deploy_lock, fcntl.LOCK_EX)
            normalize_locked_project_lock(deploy_lock)
        ensure_roots(txdir)
        if action == "journal-status":
            try:
                journal = load_journal(journal_path, node, txid, payload)
            except FileNotFoundError:
                print('{"status":"missing"}')
            else:
                print(canonical(journal).decode().strip())
            return
        if action == "prepare":
            pitr_fence(payload["maintenance_transaction_id"])
            validate_units()
            validate_role_assets(payload)
            validate_role_agent_runtime(project, node)
            baseline_primary = payload.get("baseline_primary")
            baseline_system = payload.get("baseline_system_identifier")
            baseline_timeline = payload.get("baseline_timeline")
            if (baseline_primary not in NODES
                    or not isinstance(baseline_system, str)
                    or not re.fullmatch(r"[0-9]{10,24}", baseline_system)
                    or not isinstance(baseline_timeline, str)
                    or not re.fullmatch(r"[1-9][0-9]*", baseline_timeline)):
                die("initial rollout lineage is invalid")
            try:
                journal = load_journal(journal_path, node, txid, payload)
                if not payload["resume"]:
                    die("existing transaction requires resume=true")
            except FileNotFoundError:
                baseline_dcs = yaml_config(project, compose)
                baseline_archive_command = supported_archive_command(
                    baseline_dcs, payload["legacy_command_sha256"])
                journal = {"completed": [], "current_image": payload["current_image"],
                    "baseline_archive_command": baseline_archive_command,
                    "baseline_primary": baseline_primary,
                    "baseline_system_identifier": baseline_system,
                    "baseline_timeline": int(baseline_timeline),
                    "compose_contract_sha256": payload["compose_contract_sha256"],
                    "contract_helper_sha256": payload["contract_helper_sha256"],
                    "controller_sha256": payload["controller_sha256"],
                    "deploy_sha": payload["deploy_sha"],
                    "etcd_check_sha256": payload["etcd_check_sha256"],
                    "helper_sha256": payload["helper_sha256"],
                    "legacy_command_sha256": payload["legacy_command_sha256"],
                    "maintenance_transaction_id": payload["maintenance_transaction_id"],
                    "publish_run_attempt": payload["publish_run_attempt"],
                    "publish_run_id": payload["publish_run_id"],
                    "role_agent_sha256": payload["role_agent_sha256"],
                    "role_identity_sha256": payload["role_identity_sha256"],
                    "role_unit_sha256": payload["role_unit_sha256"],
                    "node": node, "operation": "idle", "target_image": payload["target_image"],
                    "transaction_id": txid, "version": 1,
                    "dcs_baseline": baseline_dcs,
                    "dcs_baseline_sha256": sha(canonical(baseline_dcs))}
                save_journal(journal_path, journal)
            marker(marker_path, txid, create=True)
            print("prepared")
            return
        if action in {"abort", "finalize"}:
            journal = load_journal(journal_path, node, txid, payload)
            if action in journal["completed"]:
                pitr_fence(payload["maintenance_transaction_id"])
                validate_units()
                validate_role_assets(payload)
                validate_role_agent_runtime(project, node)
                os.chdir(project)
                if action == "finalize":
                    prove_final_generation(project, compose, compose_project, volume,
                                           payload, journal, node)
                else:
                    prove_aborted_generation(
                        project, compose, compose_project, volume, payload, journal)
                remove_marker_if_owned(marker_path, txid)
                print(action + "=already-passed")
                return
        marker(marker_path, txid)
        journal = load_journal(journal_path, node, txid, payload)
        if action == "status":
            print(canonical(journal).decode().strip())
            return
        operation = "record:" + str(payload.get("record")) if action == "record" else action
        if action in {"abort", "apply-archive-command", "finalize", "prove-archive",
                "revert-archive-command", "rollback-node", "switchover", "update-node"}:
            pitr_fence(payload["maintenance_transaction_id"])
            validate_units()
            validate_role_assets(payload)
            validate_role_agent_runtime(project, node)
        if operation == "record:switched-over" and journal["operation"] == "switchover":
            complete(journal_path, journal, "switchover")
        if action == "rollback-node" and journal["operation"] == "update-node":
            complete(journal_path, journal, "update-node")
        if action == "abort" and journal["operation"] == "stage":
            complete(journal_path, journal, "stage")
        if action == "revert-archive-command" and journal["operation"] == "prove-archive":
            journal["last_error"] = "archive proof failed or was interrupted"
            journal["operation"] = "idle"
            save_journal(journal_path, journal)
        if action not in READ_ACTIONS:
            begin(journal_path, journal, operation)
        os.chdir(project)
        if action == "preflight":
            preflight(project, compose, compose_project, volume, payload, node)
        elif action == "stage":
            username, token = payload.get("ghcr_username"), payload.get("ghcr_token")
            if not isinstance(username, str) or not username or not isinstance(token, str) or not token:
                die("GHCR read credentials are required")
            docker_config = tempfile.mkdtemp(prefix=".docker-", dir=txdir)
            os.chmod(docker_config, 0o700)
            environment = CLEAN_ENV.copy()
            environment["DOCKER_CONFIG"] = docker_config
            try:
                run(["docker", "login", "ghcr.io", "--username", username, "--password-stdin"],
                    stdin=token + "\n", env=environment)
                run(["docker", "pull", payload["target_image"]], env=environment)
            finally:
                try:
                    run(["docker", "logout", "ghcr.io"], ok=(0, 1), env=environment)
                finally:
                    shutil.rmtree(docker_config)
            image_attestation(payload["target_image"], payload["helper_sha256"])
        elif action in {"update-node", "rollback-node"}:
            phase = payload["update_phase"]
            if phase == "standby":
                require_completed(journal, "record:baseline-primary-" + payload["expected_primary"])
            elif phase == "former-primary":
                require_completed(journal, "record:switched-over")
            require_standby(project, compose, payload["expected_primary"],
                            allow_unavailable=action == "rollback-node")
            expected = payload["current_image"] if action == "update-node" else payload["target_image"]
            target = payload["target_image"] if action == "update-node" else payload["current_image"]
            target_helper = payload["helper_sha256"] if action == "update-node" else None
            actual = env_image(project)[0]
            if actual not in {expected, target}:
                die("PATRONI_IMAGE is outside the requested transition")
            validate_compose(project, compose, compose_project, volume, actual,
                             payload["compose_contract_sha256"], payload)
            image_attestation(target, target_helper)
            if actual == target:
                if runtime_generation_matches(project, compose, target):
                    runtime_attestation(project, compose, target, target_helper)
                    complete(journal_path, journal, action)
                    print(action + "=already-passed")
                    return
            set_env_image(project, expected, target)
            validate_compose(project, compose, compose_project, volume, target,
                             payload["compose_contract_sha256"], payload)
            require_standby(project, compose, payload["expected_primary"],
                            allow_unavailable=action == "rollback-node")
            run(compose_args(project, compose) + ["up", "-d", "--no-deps", "--force-recreate",
                "--pull", "never", "--wait", "--wait-timeout", "120", "db"])
            validate_compose(project, compose, compose_project, volume, target,
                             payload["compose_contract_sha256"], payload)
            runtime_attestation(project, compose, target, target_helper)
        elif action == "attest-target-runtime":
            validate_units()
            validate_archive(project)
            runtime_attestation(project, compose, payload["target_image"], payload["helper_sha256"])
        elif action == "attest-current-runtime":
            validate_units()
            validate_archive(project)
            validate_compose(project, compose, compose_project, volume,
                             payload["current_image"], payload["compose_contract_sha256"], payload)
            runtime_attestation(project, compose, payload["current_image"])
        elif action == "attest-runtime-ownership":
            attest_runtime_ownership(project, compose, payload["expected_role"])
        elif action == "attest-archive-runtime":
            attest_archive_runtime(project, compose, payload["target_image"], payload["helper_sha256"])
        elif action == "prove-etcd":
            prove_etcd(payload)
        elif action == "check-baseline-dcs":
            check_baseline_dcs(project, compose, journal)
        elif action == "check-legacy-dcs":
            check_legacy_dcs(project, compose, payload["legacy_command_sha256"])
        elif action == "check-target-dcs":
            check_target_dcs(project, compose, journal)
        elif action == "apply-archive-command":
            require_completed(journal, "record:former-primary-updated")
            if local_patroni_role() != "primary": die("DCS mutation requires current primary")
            prove_etcd(payload)
            apply_archive_command(project, compose, payload["legacy_command_sha256"], journal_path, journal)
        elif action == "revert-archive-command":
            if local_patroni_role() != "primary":
                die("DCS compensation requires current primary")
            prove_etcd(payload)
            revert_archive_command(project, compose, payload["legacy_command_sha256"], journal)
        elif action == "switchover":
            expected_primary = payload.get("expected_primary")
            candidate = payload.get("candidate")
            if expected_primary != node or candidate not in NODES or candidate == node:
                die("unreviewed switchover identities")
            require_completed(journal, "record:standby-updated")
            if local_patroni_role() != "primary": die("switchover source is not primary")
            prove_etcd(payload)
            check_baseline_dcs(project, compose, journal)
            identifier = container_id(project, compose)
            run(["docker", "exec", identifier, "patronictl", "-c", "/etc/patroni/patroni.yml",
                 "switchover", "mvn-postgres", "--primary", expected_primary,
                 "--candidate", candidate, "--force"])
        elif action == "prove-archive":
            require_completed(journal, "record:archive-command-applied")
            if local_patroni_role() != "primary": die("archive proof requires current primary")
            print(prove_archive(project, compose))
        elif action == "record":
            record = payload.get("record")
            if record not in RECORDS:
                die("unreviewed rollout record")
            complete(journal_path, journal, operation)
            print(record)
            return
        elif action == "finalize":
            prove_final_generation(project, compose, compose_project, volume,
                                   payload, journal, node)
            complete(journal_path, journal, action)
            remove_marker_if_owned(marker_path, txid)
            print(action + "=passed")
            return
        elif action == "abort":
            prove_aborted_generation(
                project, compose, compose_project, volume, payload, journal)
            complete(journal_path, journal, action)
            remove_marker_if_owned(marker_path, txid)
            print(action + "=passed")
            return
        else:
            die("unsupported rollout action")
        if action not in READ_ACTIONS:
            complete(journal_path, journal, action)
        print(action + "=passed")
    finally:
        if deploy_lock is not None:
            os.close(deploy_lock)
        os.close(lock)

try:
    main()
except Exception as exc:
    print("patroni_rollout_remote status=failed error=" + str(exc), file=sys.stderr)
    raise SystemExit(1)
'''
