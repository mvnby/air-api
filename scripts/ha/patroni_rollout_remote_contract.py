"""Payload and journal contract embedded into the Patroni rollout executor."""

REMOTE_CONTRACT = r'''
def validate_payload(payload):
    required = {"compose_contract_sha256", "contract_helper_b64", "contract_helper_sha256",
                "controller_sha256", "current_image", "deploy_sha", "helper_sha256",
                "etcd_check_b64", "etcd_check_sha256", "legacy_command_sha256",
                "maintenance_transaction_id", "publish_run_attempt", "publish_run_id",
                "resume", "role_agent_sha256", "role_agent_config_sha256",
                "role_compose_runtime_sha256",
                "role_identity_sha256", "role_unit_sha256", "target_image"}
    if not isinstance(payload, dict) or not required.issubset(payload):
        die("invalid rollout payload")
    if not IMAGE_RE.fullmatch(payload["current_image"]) or not IMAGE_RE.fullmatch(payload["target_image"]):
        die("rollout images must be immutable reviewed digests")
    if payload["current_image"] == payload["target_image"]:
        die("rollout images must differ")
    if type(payload.get("resume")) is not bool:
        die("rollout resume flag is invalid")
    if payload["legacy_command_sha256"] != LEGACY_COMMAND_SHA256 or sha(LEGACY_COMMAND) != LEGACY_COMMAND_SHA256:
        die("legacy archive command is not the compiled reviewed generation")
    for key in ("compose_contract_sha256", "contract_helper_sha256", "controller_sha256",
                "etcd_check_sha256", "helper_sha256", "legacy_command_sha256",
                "role_agent_sha256", "role_agent_config_sha256",
                "role_compose_runtime_sha256", "role_identity_sha256",
                "role_unit_sha256"):
        if not isinstance(payload[key], str) or not DIGEST_RE.fullmatch(payload[key]):
            die("invalid rollout digest: " + key)
    if not isinstance(payload["deploy_sha"], str) or not re.fullmatch(r"[0-9a-f]{40}", payload["deploy_sha"]):
        die("invalid tested deploy SHA")
    if (not isinstance(payload["publish_run_id"], str)
            or not re.fullmatch(r"[1-9][0-9]{5,14}", payload["publish_run_id"])):
        die("invalid publish run ID")
    if (type(payload["publish_run_attempt"]) is not int
            or not 1 <= payload["publish_run_attempt"] <= 2147483647):
        die("invalid publish run attempt")
    if not isinstance(payload["maintenance_transaction_id"], str) or not TX_RE.fullmatch(payload["maintenance_transaction_id"]):
        die("invalid PITR maintenance transaction ID")
    try:
        source = base64.b64decode(payload["contract_helper_b64"], validate=True)
    except (binascii.Error, TypeError, ValueError):
        die("invalid Compose contract helper encoding")
    if len(source) > 32768 or sha(source) != payload["contract_helper_sha256"]:
        die("Compose contract helper digest mismatch")
    compile(source, "<patroni-compose-contract>", "exec")
    try:
        etcd_source = base64.b64decode(payload["etcd_check_b64"], validate=True)
    except (binascii.Error, TypeError, ValueError):
        die("invalid etcd check encoding")
    if len(etcd_source) > 32768 or sha(etcd_source) != payload["etcd_check_sha256"]:
        die("etcd check digest mismatch")

def validate_action(action, payload):
    base = {"compose_contract_sha256", "contract_helper_b64", "contract_helper_sha256",
        "controller_sha256", "current_image", "deploy_sha", "etcd_check_b64",
        "etcd_check_sha256", "helper_sha256", "legacy_command_sha256", "resume",
        "maintenance_transaction_id", "publish_run_attempt", "publish_run_id",
        "role_agent_sha256", "role_agent_config_sha256",
        "role_compose_runtime_sha256", "role_identity_sha256",
        "role_unit_sha256", "target_image"}
    extras = {
        "prepare": {"baseline_primary", "baseline_system_identifier", "baseline_timeline"},
        "record": {"record"}, "stage": {"ghcr_token", "ghcr_username"},
        "attest-runtime-ownership": {"expected_role"},
        "switchover": {"candidate", "expected_primary"},
        "update-node": {"expected_primary", "expected_role", "update_phase"},
        "rollback-node": {"expected_primary", "expected_role", "update_phase"},
    }
    allowed = {"abort", "apply-archive-command", "attest-archive-runtime",
        "attest-current-runtime", "attest-runtime-ownership", "attest-target-runtime",
        "check-legacy-dcs", "check-target-dcs", "finalize",
        "journal-status", "prepare", "preflight", "prove-archive", "prove-etcd", "record",
        "revert-archive-command", "rollback-node", "stage", "status", "switchover", "update-node"}
    if action not in allowed or set(payload) != base | extras.get(action, set()):
        die("unsupported rollout action or payload fields")
    if action == "record" and payload["record"] not in RECORDS:
        die("unreviewed rollout record")
    if action == "switchover" and (payload["expected_primary"] not in NODES
            or payload["candidate"] not in NODES or payload["candidate"] == payload["expected_primary"]):
        die("unreviewed switchover identities")
    if action in {"update-node", "rollback-node"}:
        if (payload["expected_primary"] not in NODES or payload["expected_role"] != "standby"
                or payload["update_phase"] not in {"standby", "former-primary", "rollback"}):
            die("unreviewed node update role contract")
    if action == "attest-runtime-ownership" and payload["expected_role"] not in {"primary", "standby"}:
        die("unreviewed runtime ownership role")

def paths(node, txid):
    if node not in NODES or not TX_RE.fullmatch(txid):
        die("unreviewed node or transaction")
    project, compose, compose_project, volume = NODES[node]
    txdir = TX_ROOT + "/" + txid + "-" + node
    return project, compose, compose_project, volume, txdir, txdir + "/journal.json", project + "/.patroni-cutover-in-progress"

def ensure_roots(txdir):
    safe_dir(STATE_ROOT, 0o700)
    safe_dir(TX_ROOT, 0o700)
    safe_dir(txdir, 0o700)

def marker(marker_path, txid, create=False):
    expected = (txid + "\n").encode()
    try:
        content = read_root_file(marker_path)
    except FileNotFoundError:
        if not create:
            die("Patroni cutover marker is missing")
        atomic(marker_path, expected)
        return
    if content != expected:
        die("another transaction owns the Patroni cutover marker")

def remove_marker_if_owned(marker_path, txid):
    try:
        content = read_root_file(marker_path)
    except FileNotFoundError:
        return
    if content != (txid + "\n").encode("ascii"):
        die("another transaction owns the Patroni cutover marker")
    os.unlink(marker_path)

def pitr_fence(maintenance_transaction_id):
    content = read_root_file(PITR_MARKER)
    if content != (maintenance_transaction_id + "\n").encode("ascii"):
        die("PITR maintenance fence does not match the reviewed transaction")

def load_journal(path, node, txid, payload):
    raw = read_root_file(path)
    data = json.loads(raw)
    expected = {
        "current_image": payload["current_image"], "node": node,
        "target_image": payload["target_image"], "transaction_id": txid,
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
        "role_agent_config_sha256": payload["role_agent_config_sha256"],
        "role_compose_runtime_sha256": payload["role_compose_runtime_sha256"],
        "role_identity_sha256": payload["role_identity_sha256"],
        "role_unit_sha256": payload["role_unit_sha256"],
    }
    if (not isinstance(data, dict) or data.get("version") != 1
            or any(data.get(key) != value for key, value in expected.items())
            or not {"baseline_archive_command", "dcs_baseline",
                    "dcs_baseline_sha256"}.issubset(data)
            or not isinstance(data.get("completed"), list)
            or not isinstance(data.get("operation"), str)
            or len(data["completed"]) != len(set(data["completed"]))
            or any(item not in COMPLETED for item in data["completed"])
            or data["operation"] not in ({"idle"} | COMPLETED)):
        die("rollout journal contract mismatch")
    allowed = set(expected) | {"baseline_archive_command", "baseline_primary",
        "baseline_system_identifier", "baseline_timeline", "completed", "dcs_baseline",
        "dcs_baseline_sha256", "last_error", "legacy_archive_command", "operation", "version"}
    if set(data) - allowed or raw != canonical(data):
        die("rollout journal is not canonical or has extra fields")
    return data

def save_journal(path, journal):
    atomic(path, canonical(journal))

def begin(path, journal, operation):
    if journal["operation"] not in {"idle", operation}:
        die("another interrupted rollout action must be reconciled first")
    journal["operation"] = operation
    save_journal(path, journal)

def complete(path, journal, operation):
    if operation not in journal["completed"]:
        journal["completed"].append(operation)
    journal["operation"] = "idle"
    save_journal(path, journal)

def require_completed(journal, *entries):
    missing = [entry for entry in entries if entry not in journal["completed"]]
    if missing:
        die("rollout journal prerequisite is missing: " + ",".join(missing))
'''
