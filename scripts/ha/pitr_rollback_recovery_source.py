"""Rollback receipt support embedded in the remote PITR release executor."""
from __future__ import annotations


REMOTE_ROLLBACK_RECOVERY_SUPPORT = r'''
def rollback_receipt(journal):
    generations = []
    for entry in journal["entries"]:
        old = entry["old"]
        generations.append({"mode": entry["mode"], "path": entry["path"],
                            "present": old["present"], "sha256": old.get("sha256")})
    return {"old_generations": generations, "project_dir": journal["project_dir"],
            "release_sha256": journal["release_sha256"], "txid": journal["txid"], "version": 1}
def validate_rollback_receipt(receipt, txid, project_dir, modes, release=None):
    release_digest = receipt.get("release_sha256") if isinstance(receipt, dict) else None
    if (not isinstance(receipt, dict)
            or set(receipt) != {"old_generations", "project_dir", "release_sha256", "txid", "version"}
            or type(receipt["version"]) is not int or receipt["version"] != 1
            or receipt["txid"] != txid
            or receipt["project_dir"] != project_dir
            or not isinstance(release_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", release_digest)
            or not isinstance(receipt["old_generations"], list)):
        raise RuntimeError("rollback receipt contract is invalid")
    if release is not None and release_digest != release:
        raise RuntimeError("rollback receipt belongs to another release")
    paths = []
    for generation in receipt["old_generations"]:
        path = generation.get("path") if isinstance(generation, dict) else None
        if (not isinstance(generation, dict)
                or set(generation) != {"mode", "path", "present", "sha256"}
                or not isinstance(path, str) or path not in modes or path in paths
                or generation["mode"] != modes[path]
                or type(generation["present"]) is not bool):
            raise RuntimeError("rollback receipt generation is invalid")
        if generation["present"]:
            if (not isinstance(generation["sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", generation["sha256"])):
                raise RuntimeError("rollback receipt generation digest is invalid")
        elif generation["sha256"] is not None:
            raise RuntimeError("absent rollback generation has a digest")
        paths.append(path)
    if paths != sorted(modes):
        raise RuntimeError("rollback receipt path set is incomplete")
def rollback_receipt_path(txid):
    return os.path.join(ROLLBACK_RECEIPT_ROOT, txid + ".json")
def read_rollback_receipt(txid, project_dir, modes, release=None):
    content, _ = read_regular(rollback_receipt_path(txid), exact_mode=0o600, max_bytes=MAX_BUNDLE)
    try:
        receipt = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("rollback receipt is invalid") from exc
    if content != canonical(receipt) + b"\n":
        raise RuntimeError("rollback receipt is not canonical")
    validate_rollback_receipt(receipt, txid, project_dir, modes, release)
    return receipt
def write_rollback_receipt(receipt, modes):
    validate_rollback_receipt(receipt, receipt["txid"], receipt["project_dir"], modes)
    path = rollback_receipt_path(receipt["txid"])
    expected = canonical(receipt) + b"\n"
    try:
        existing, _ = read_regular(path, exact_mode=0o600, max_bytes=MAX_BUNDLE)
    except FileNotFoundError:
        atomic_write(path, expected, 0o600)
    else:
        if existing != expected:
            raise RuntimeError("rollback receipt conflicts with this transaction")
    return read_rollback_receipt(receipt["txid"], receipt["project_dir"], modes)
def verify_rollback_generations(receipt):
    for generation in receipt["old_generations"]:
        try:
            content, _ = read_regular(generation["path"], exact_mode=generation["mode"])
        except FileNotFoundError:
            if generation["present"]:
                raise RuntimeError("recorded rollback generation is missing: " + generation["path"])
            continue
        if (not generation["present"]
                or hashlib.sha256(content).hexdigest() != generation["sha256"]):
            raise RuntimeError("recorded rollback generation does not match: " + generation["path"])
'''.strip() + "\n"
