"""Pinned read-mostly remote proof for one fenced Patroni preflight incident."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

try:
    from scripts.ha.patroni_rollout_schema import canonical_json
    from scripts.ha.pitr_pinned_ssh import PatroniNode, PinnedSshContext, ssh_args
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from patroni_rollout_schema import canonical_json  # type: ignore[no-redef]
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSFORMER_SOURCE = REPO_ROOT / "scripts/ha/patroni_preflight_incident_recovery.py"
CONTRACT_HELPER_SOURCE = REPO_ROOT / "scripts/ha/patroni_compose_db_contract.py"
ACTIONS = {"probe", "terminalize", "unfence"}


REMOTE_EXECUTOR = r'''
import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import types
from pathlib import Path

ROOT = 0
STATE_ROOT = "/var/lib/mvn-patroni-rollout"
TX_ROOT = STATE_ROOT + "/transactions"
RECEIPT_ROOT = STATE_ROOT + "/transactions-receipts"
LOCK_PATH = "/run/lock/mvn-patroni-rollout.lock"
PITR_MARKER = "/run/mvn-postgres-pitr-maintenance"
LEGACY_COMMAND = "test ! -f /postgres-wal-archive/%f && cp %p /postgres-wal-archive/%f || test -f /postgres-wal-archive/%f"
NODES = {
    "mvn-api": ("/opt/air-api", "docker-compose.patroni.yml", "air-api", "air-api_postgres_data"),
    "zakup": ("/opt/mvn-reserve", "docker-compose.patroni.yml", "mvn_reserve", "mvn_reserve_postgres_data"),
}
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
TX_RE = re.compile(r"[0-9a-f]{32}")
IMAGE_RE = re.compile(r"ghcr[.]io/mvnby/air-api/patroni@sha256:[0-9a-f]{64}")
CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root", "LANG": "C", "LC_ALL": "C", "DOCKER_CONTEXT": "default",
}

def die(message):
    raise RuntimeError(message)

def sha(raw):
    if isinstance(raw, str): raw = raw.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def allowed_command(args):
    compose_tails = (
        ["ps", "-q", "db"],
        ["config", "--format", "json"],
        ["config", "--no-env-resolution", "--no-interpolate", "--format", "json"],
    )
    for project, compose, compose_project, _volume in NODES.values():
        prefix = ["docker", "compose", "--project-name", compose_project,
            "--project-directory", project, "-f", project + "/" + compose]
        if any(args == prefix + tail for tail in compose_tails): return True
    if (len(args) == 3 and args[:2] == ["docker", "inspect"]
            and re.fullmatch(r"[0-9a-f]{12,64}", args[2])): return True
    if (len(args) == 4 and args[:3] == ["docker", "image", "inspect"]
            and IMAGE_RE.fullmatch(args[3])): return True
    if args == ["curl", "-fsS", "--max-time", "5", "http://127.0.0.1:8008/config"]:
        return True
    units = {"mvn-postgres-wal-upload.timer", "mvn-postgres-wal-upload.service",
        "mvn-postgres-basebackup.timer", "mvn-postgres-basebackup.service"}
    if (len(args) == 5 and args[:4] == ["systemctl", "show", "--property=ActiveState",
            "--value"] and args[4] in units): return True
    return len(args) == 4 and args[:3] == ["/usr/bin/python3", "-I", "-c"]

def run(args, *, stdin=None):
    if not allowed_command(args):
        die("incident recovery command is outside the read-only allowlist")
    result = subprocess.run(args, input=stdin, text=True, capture_output=True,
        check=False, timeout=180, env=CLEAN_ENV)
    if result.returncode != 0:
        die((result.stderr or result.stdout or "read-only command failed").strip())
    return result.stdout.strip()

def root_dir(path, mode):
    metadata = os.lstat(path)
    if (not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != ROOT or metadata.st_gid != ROOT
            or stat.S_IMODE(metadata.st_mode) != mode):
        die("unsafe incident recovery directory: " + path)

def fsync_dir(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)

def ensure_receipt_root():
    root_dir(STATE_ROOT, 0o700)
    created = False
    try:
        os.mkdir(RECEIPT_ROOT, 0o700)
        created = True
    except FileExistsError:
        pass
    root_dir(RECEIPT_ROOT, 0o700)
    if created: fsync_dir(STATE_ROOT)

def stable_file(path, *, mode=None, maximum=1048576, root_only=False):
    before = os.lstat(path)
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1 or before.st_size > maximum
            or before.st_mode & 0o022
            or (mode is not None and stat.S_IMODE(before.st_mode) != mode)
            or (root_only and (before.st_uid != ROOT or before.st_gid != ROOT))):
        die("unsafe incident recovery file: " + path)
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            die("incident recovery file changed while opening: " + path)
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum or os.read(descriptor, 1):
            die("incident recovery file exceeds limit: " + path)
        after = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if tuple(getattr(after, x) for x in fields) != tuple(getattr(opened, x) for x in fields):
            die("incident recovery file changed while reading: " + path)
        return raw
    finally:
        os.close(descriptor)

def owned_marker(path, expected, *, allow_missing=False):
    try:
        raw = stable_file(path, mode=0o600, maximum=128, root_only=True)
    except FileNotFoundError:
        if allow_missing: return False
        raise
    if raw != (expected + "\n").encode("ascii"):
        die("incident recovery marker belongs to another transaction")
    return True

def open_lock(path, *, project=False):
    before = os.lstat(path)
    expected_modes = {0o600} if not project else {0o600, 0o644}
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or before.st_uid != ROOT or before.st_gid != ROOT or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) not in expected_modes):
        die("unsafe incident recovery lock: " + path)
    descriptor = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino, opened.st_nlink) != (before.st_dev, before.st_ino, 1):
        os.close(descriptor); die("incident recovery lock changed while opening")
    return descriptor

def compose_args(project, compose, compose_project):
    return ["docker", "compose", "--project-name", compose_project,
        "--project-directory", project, "-f", project + "/" + compose]

def env_image(project):
    content = stable_file(project + "/.env", maximum=1048576).decode("utf-8")
    values = [line.split("=", 1)[1] for line in content.splitlines()
              if line.startswith("PATRONI_IMAGE=")]
    if len(values) != 1 or not IMAGE_RE.fullmatch(values[0]):
        die("incident recovery found an invalid PATRONI_IMAGE")
    return values[0]

def container_id(project, compose, compose_project):
    identifiers = run(compose_args(project, compose, compose_project) + ["ps", "-q", "db"]).splitlines()
    if len(identifiers) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", identifiers[0]):
        die("incident recovery requires exactly one db container")
    inspected = json.loads(run(["docker", "inspect", identifiers[0]]))
    if (not isinstance(inspected, list) or len(inspected) != 1
            or inspected[0].get("State", {}).get("Running") is not True
            or inspected[0].get("State", {}).get("Health", {}).get("Status") != "healthy"):
        die("incident recovery db container is not healthy")
    return identifiers[0]

def prove_runtime(project, compose, compose_project, expected_image):
    if env_image(project) != expected_image:
        die("incident recovery current image drifted in .env")
    identifier = container_id(project, compose, compose_project)
    inspected = json.loads(run(["docker", "inspect", identifier]))[0]
    if inspected.get("Config", {}).get("Image") != expected_image:
        die("incident recovery container image reference drifted")
    image = json.loads(run(["docker", "image", "inspect", expected_image]))
    if (not isinstance(image, list) or len(image) != 1
            or inspected.get("Image") != image[0].get("Id")
            or expected_image not in image[0].get("RepoDigests", [])):
        die("incident recovery runtime image identity drifted")

def prove_compose(project, compose, compose_project, volume, payload):
    source = project + "/" + compose
    if sha(stable_file(source, maximum=1048576)) != payload["compose_source_sha256"]:
        die("incident recovery Compose source drifted")
    args = compose_args(project, compose, compose_project)
    unrendered = run(args + ["config", "--no-env-resolution", "--no-interpolate", "--format", "json"])
    helper = base64.b64decode(payload["contract_helper_b64"], validate=True).decode("utf-8")
    measured = run(["/usr/bin/python3", "-I", "-c", helper], stdin=unrendered)
    if measured != payload["compose_contract_sha256"]:
        die("incident recovery corrected Compose contract drifted")
    config = json.loads(run(args + ["config", "--format", "json"]))
    db = config.get("services", {}).get("db", {})
    mounts = [item for item in db.get("volumes", [])
              if item.get("target") == "/var/lib/postgresql/data"]
    top = config.get("volumes", {}).get("postgres_data", {})
    if (config.get("name") != compose_project or db.get("image") != payload["current_image"]
            or len(mounts) != 1 or mounts[0].get("source") != "postgres_data"
            or mounts[0].get("type") != "volume" or top.get("name") != volume
            or top.get("external") is not True):
        die("incident recovery resolved Compose identity drifted")

def prove_legacy_dcs():
    config = json.loads(run(["curl", "-fsS", "--max-time", "5",
        "http://127.0.0.1:8008/config"]))
    parameters = config.get("postgresql", {}).get("parameters", {})
    actual = {key: str(parameters.get(key, ""))
              for key in ("archive_mode", "archive_timeout", "archive_command")}
    expected = {"archive_mode": "on", "archive_timeout": "300",
        "archive_command": LEGACY_COMMAND}
    if actual != expected:
        die("incident recovery DCS is not the exact legacy generation")

def prove_units():
    for unit in ("mvn-postgres-wal-upload.timer", "mvn-postgres-wal-upload.service",
                 "mvn-postgres-basebackup.timer", "mvn-postgres-basebackup.service"):
        state = run(["systemctl", "show", "--property=ActiveState", "--value", unit])
        if state != "inactive": die("PITR unit escaped the maintenance fence: " + unit)

def validate_payload(payload, node, txid):
    required = {"baseline_primary", "baseline_system_identifier", "baseline_timeline",
        "compose_contract_sha256", "compose_source_sha256", "contract_helper_b64",
        "contract_helper_sha256", "current_image", "incident_controller_sha256",
        "incident_deploy_sha", "journal_after_sha256", "journal_before_operation",
        "journal_before_sha256", "journal_compose_contract_sha256",
        "maintenance_transaction_id", "publish_run_attempt", "publish_run_id",
        "recovery_deploy_sha", "target_image", "transaction_id", "transformer_b64",
        "transformer_sha256"}
    if not isinstance(payload, dict) or set(payload) != required:
        die("incident recovery payload fields are not exact")
    if node not in NODES or payload["transaction_id"] != txid or not TX_RE.fullmatch(txid):
        die("incident recovery transaction identity is invalid")
    for key in ("compose_contract_sha256", "compose_source_sha256",
                "contract_helper_sha256", "incident_controller_sha256",
                "journal_after_sha256", "journal_before_sha256",
                "journal_compose_contract_sha256", "transformer_sha256"):
        if not isinstance(payload[key], str) or not DIGEST_RE.fullmatch(payload[key]):
            die("incident recovery digest is invalid: " + key)
    if (not COMMIT_RE.fullmatch(payload["recovery_deploy_sha"])
            or not COMMIT_RE.fullmatch(payload["incident_deploy_sha"])
            or not TX_RE.fullmatch(payload["maintenance_transaction_id"])
            or not IMAGE_RE.fullmatch(payload["current_image"])
            or not IMAGE_RE.fullmatch(payload["target_image"])
            or payload["current_image"] == payload["target_image"]):
        die("incident recovery generation identity is invalid")
    if payload["baseline_primary"] not in NODES or payload["baseline_timeline"] != 9:
        die("incident recovery baseline topology is invalid")
    if not re.fullmatch(r"[0-9]{10,24}", payload["baseline_system_identifier"]):
        die("incident recovery system identifier is invalid")
    if payload["journal_before_operation"] not in {"idle", "abort"}:
        die("incident recovery journal operation is invalid")
    if (not isinstance(payload["publish_run_id"], str)
            or not re.fullmatch(r"[1-9][0-9]{5,14}", payload["publish_run_id"])
            or type(payload["publish_run_attempt"]) is not int
            or payload["publish_run_attempt"] < 1):
        die("incident recovery publish evidence is invalid")
    for encoded, digest in (("transformer_b64", "transformer_sha256"),
                            ("contract_helper_b64", "contract_helper_sha256")):
        try: source = base64.b64decode(payload[encoded], validate=True)
        except (binascii.Error, TypeError, ValueError): die("incident recovery source encoding is invalid")
        if len(source) > 65536 or sha(source) != payload[digest]:
            die("incident recovery reviewed source digest drifted")

def load_transformer(payload, node):
    source = base64.b64decode(payload["transformer_b64"], validate=True)
    module_name = "patroni_preflight_incident_recovery_embedded"
    module = types.ModuleType(module_name)
    sys.modules[module_name] = module
    namespace = module.__dict__
    exec(compile(source, "<patroni-preflight-incident-recovery>", "exec"), namespace)
    contract = namespace["IncidentJournalContract"](
        node=node, before_sha256=payload["journal_before_sha256"],
        after_sha256=payload["journal_after_sha256"],
        before_operation=payload["journal_before_operation"],
        baseline_primary=payload["baseline_primary"])
    reviewed = namespace["INCIDENT_CONTRACTS"].get(node)
    if reviewed != contract or namespace["EXPECTED_CONTROLLER_SHA256"] != payload["incident_controller_sha256"]:
        die("embedded incident transformer contract drifted")
    return namespace, contract

def journal_path(node, txid):
    return TX_ROOT + "/" + txid + "-" + node + "/journal.json"

def receipt_path(node, txid):
    return RECEIPT_ROOT + "/" + txid + "-" + node + "-preflight-recovery.json"

def validate_journal_evidence(state, payload, node):
    journal = state.journal
    expected = {"baseline_primary": payload["baseline_primary"],
        "baseline_system_identifier": payload["baseline_system_identifier"],
        "baseline_timeline": payload["baseline_timeline"],
        "compose_contract_sha256": payload["journal_compose_contract_sha256"],
        "controller_sha256": payload["incident_controller_sha256"],
        "current_image": payload["current_image"], "deploy_sha": payload["incident_deploy_sha"],
        "maintenance_transaction_id": payload["maintenance_transaction_id"],
        "node": node, "publish_run_attempt": payload["publish_run_attempt"],
        "publish_run_id": payload["publish_run_id"], "target_image": payload["target_image"],
        "transaction_id": payload["transaction_id"]}
    if any(journal.get(key) != value for key, value in expected.items()):
        die("incident journal evidence differs from the reviewed manifest")

def expected_receipt(namespace, contract, payload):
    return namespace["receipt_document"](contract,
        transaction_id=payload["transaction_id"],
        maintenance_transaction_id=payload["maintenance_transaction_id"],
        recovery_deploy_sha=payload["recovery_deploy_sha"],
        current_image=payload["current_image"],
        corrected_compose_contract_sha256=payload["compose_contract_sha256"],
        compose_source_sha256=payload["compose_source_sha256"],
        incident_controller_sha256=payload["incident_controller_sha256"])

def prove(node, payload, *, marker_may_be_absent=False, receipt_required=False,
          receipt_may_be_missing=False):
    project, compose, compose_project, volume = NODES[node]
    namespace, contract = load_transformer(payload, node)
    root_dir(STATE_ROOT, 0o700); root_dir(TX_ROOT, 0o700); ensure_receipt_root()
    root_dir(os.path.dirname(journal_path(node, payload["transaction_id"])), 0o700)
    owned_marker(PITR_MARKER, payload["maintenance_transaction_id"])
    marker = project + "/.patroni-cutover-in-progress"
    marker_present = owned_marker(marker, payload["transaction_id"], allow_missing=marker_may_be_absent)
    state = namespace["validate_journal"](
        stable_file(journal_path(node, payload["transaction_id"]), mode=0o600, root_only=True), contract)
    validate_journal_evidence(state, payload, node)
    prove_compose(project, compose, compose_project, volume, payload)
    prove_runtime(project, compose, compose_project, payload["current_image"])
    prove_legacy_dcs(); prove_units()
    receipt = expected_receipt(namespace, contract, payload)
    receipt_present = False
    try:
        raw_receipt = stable_file(receipt_path(node, payload["transaction_id"]),
                                  mode=0o600, maximum=16384, root_only=True)
    except FileNotFoundError:
        if receipt_required or (state.state == "after" and not receipt_may_be_missing):
            die("terminal incident journal has no exact recovery receipt")
    else:
        if raw_receipt != namespace["canonical_json"](receipt):
            die("incident recovery receipt drifted")
        receipt_present = True
    if not marker_present and (state.state != "after" or not receipt_present):
        die("missing cutover marker is not backed by a terminal incident receipt")
    return namespace, contract, state, marker, marker_present, receipt, receipt_present

def main():
    if os.geteuid() != ROOT or len(sys.argv) != 4: die("incident recovery requires root and exact arguments")
    action, node, txid = sys.argv[1:]
    if action not in {"probe", "terminalize", "unfence"}: die("unsupported incident recovery action")
    raw = sys.stdin.buffer.read(131073)
    if not raw or len(raw) > 131072: die("incident recovery payload size is invalid")
    payload = json.loads(raw); validate_payload(payload, node, txid)
    project = NODES[node][0]
    rollout_lock = open_lock(LOCK_PATH)
    project_lock = open_lock(project + "/.deploy.lock", project=True)
    try:
        fcntl.flock(rollout_lock, fcntl.LOCK_EX); fcntl.flock(project_lock, fcntl.LOCK_EX)
        namespace, contract, state, marker, marker_present, receipt, receipt_present = prove(
            node, payload, marker_may_be_absent=action in {"probe", "unfence"},
            receipt_required=action == "unfence",
            receipt_may_be_missing=action in {"probe", "terminalize"})
        if action == "terminalize":
            state = namespace["terminalize_journal"](Path(journal_path(node, txid)), contract)
            validate_journal_evidence(state, payload, node)
            namespace["ensure_root_receipt"](Path(receipt_path(node, txid)), receipt)
            receipt_present = True
        elif action == "unfence":
            if state.state != "after" or not receipt_present:
                die("incident recovery cannot unfence a nonterminal journal")
            if marker_present:
                os.unlink(marker); fsync_dir(project)
                try: os.lstat(marker)
                except FileNotFoundError: pass
                else: die("incident cutover marker removal was not durable")
        print(json.dumps({"journal_state": state.state, "marker_present":
            marker_present if action != "unfence" else False,
            "node": node, "receipt_present": receipt_present},
            sort_keys=True, separators=(",", ":")))
    finally:
        os.close(project_lock); os.close(rollout_lock)

try:
    main()
except Exception as exc:
    print("patroni_preflight_recovery_status=failed error=" + str(exc), file=sys.stderr)
    raise SystemExit(1)
'''


def _read_reviewed_source(path: Path) -> bytes:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise RuntimeError(f"unsafe local recovery source: {path}")
    return path.read_bytes()


def build_payload(
    *,
    manifest: Mapping[str, object],
    node: PatroniNode,
    recovery_deploy_sha: str,
) -> str:
    nodes = manifest.get("nodes")
    if not isinstance(nodes, Mapping) or not isinstance(nodes.get(node.alias), Mapping):
        raise RuntimeError("incident manifest lacks a reviewed node contract")
    node_contract = nodes[node.alias]
    baseline = manifest.get("baseline")
    if not isinstance(baseline, Mapping):
        raise RuntimeError("incident manifest lacks a reviewed baseline")
    transformer = _read_reviewed_source(TRANSFORMER_SOURCE)
    contract_helper = _read_reviewed_source(CONTRACT_HELPER_SOURCE)
    payload = {
        "baseline_primary": baseline.get("primary"),
        "baseline_system_identifier": baseline.get("system_identifier"),
        "baseline_timeline": baseline.get("timeline"),
        "compose_contract_sha256": node_contract.get("compose_contract_sha256"),
        "compose_source_sha256": node_contract.get("compose_source_sha256"),
        "contract_helper_b64": base64.b64encode(contract_helper).decode("ascii"),
        "contract_helper_sha256": hashlib.sha256(contract_helper).hexdigest(),
        "current_image": manifest.get("current_image"),
        "incident_controller_sha256": manifest.get("rollout_controller_sha256"),
        "incident_deploy_sha": manifest.get("incident_deploy_sha"),
        "journal_after_sha256": node_contract.get("journal_after_sha256"),
        "journal_before_operation": node_contract.get("journal_before_operation"),
        "journal_before_sha256": node_contract.get("journal_before_sha256"),
        "journal_compose_contract_sha256": node_contract.get(
            "journal_compose_contract_sha256"
        ),
        "maintenance_transaction_id": manifest.get("maintenance_transaction_id"),
        "publish_run_attempt": manifest.get("publish_run_attempt"),
        "publish_run_id": manifest.get("publish_run_id"),
        "recovery_deploy_sha": recovery_deploy_sha,
        "target_image": manifest.get("target_image"),
        "transaction_id": manifest.get("transaction_id"),
        "transformer_b64": base64.b64encode(transformer).decode("ascii"),
        "transformer_sha256": hashlib.sha256(transformer).hexdigest(),
    }
    return canonical_json(payload)


def run_remote_action(
    *,
    action: str,
    manifest: Mapping[str, object],
    node: PatroniNode,
    context: PinnedSshContext,
    recovery_deploy_sha: str,
    runner,
) -> Mapping[str, object]:
    if action not in ACTIONS:
        raise RuntimeError(f"unsupported incident recovery action: {action}")
    transaction_id = str(manifest.get("transaction_id", ""))
    command = " ".join(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            shlex.quote(REMOTE_EXECUTOR),
            action,
            node.alias,
            transaction_id,
        ]
    )
    result = runner(
        [*ssh_args(node, context), command],
        build_payload(
            manifest=manifest, node=node, recovery_deploy_sha=recovery_deploy_sha
        ),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "remote incident recovery failed").strip()
        raise RuntimeError(f"{node.alias} {action}: {detail}")
    try:
        output = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError(f"{node.alias} returned invalid recovery JSON") from exc
    if not isinstance(output, Mapping) or output.get("node") != node.alias:
        raise RuntimeError(f"{node.alias} returned an invalid recovery result")
    return output
