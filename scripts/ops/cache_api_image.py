#!/usr/bin/env python3
"""Cache one immutable API image on the primary without activating it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ha.pitr_cluster_topology import discover_cluster_topology  # noqa: E402
from scripts.ha.pitr_pinned_ssh import (  # noqa: E402
    PATRONI_NODES,
    create_context,
    ssh_args,
    ssh_subprocess_environment,
    validate_effective_config,
)

IMAGE_RE = re.compile(r"ghcr\.io/mvnby/air-api/backend@sha256:[0-9a-f]{64}")
REMOTE_HELPER = "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py"


def run(command, stdin=None):
    return subprocess.run(
        command, input=stdin, text=True, capture_output=True,
        timeout=420, env=ssh_subprocess_environment(),
    )


def remote_command(node, image: str) -> str:
    if node not in PATRONI_NODES or not IMAGE_RE.fullmatch(image):
        raise ValueError("Only an immutable API image and a pinned node are allowed")
    guarded = (REPO_ROOT / "scripts/ops/cache_api_image_remote.py").read_text()
    guarded += f"\ncache_image({node.project_dir!r}, {image!r})\n"
    helper_sha = hashlib.sha256(
        (REPO_ROOT / "scripts/ha/safe_deploy_lock.py").read_bytes()
    ).hexdigest()
    outer = f"""
import hashlib,os,stat,subprocess,sys
from pathlib import Path
helper=Path({REMOTE_HELPER!r})
metadata=helper.lstat()
if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or metadata.st_uid!=0 or metadata.st_nlink!=1 or metadata.st_mode&0o022:
    raise RuntimeError('Unsafe deployment lock helper')
if hashlib.sha256(helper.read_bytes()).hexdigest()!={helper_sha!r}:
    raise RuntimeError('Deployment lock helper differs from reviewed source')
environment=os.environ.copy()
environment['API_DEPLOY_LOCK_HELPER_SHA256']={helper_sha!r}
result=subprocess.run([sys.executable,str(helper),'exec-wait',{node.project_dir + '/.deploy.lock'!r},sys.executable,'-c',{guarded!r}],env=environment)
raise SystemExit(result.returncode)
"""
    return "python3 -c " + shlex.quote(outer)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--identity-file", type=Path, required=True)
    args = parser.parse_args()
    if not IMAGE_RE.fullmatch(args.image):
        parser.error("--image must be the exact MVN API sha256 reference")
    username = os.environ.get("GITHUB_ACTOR", "")
    token = sys.stdin.read(8193).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", username) or not token or len(token)>8192 or any(c.isspace() for c in token):
        parser.error("Registry credentials must arrive through stdin")
    with tempfile.TemporaryDirectory(prefix="mvn-api-image-ssh-") as directory:
        context = create_context(Path(directory), args.identity_file)
        for node in PATRONI_NODES:
            validate_effective_config(node, context)
        topology = discover_cluster_topology(context=context, runner=run)
        result = run(
            [*ssh_args(topology.primary, context), remote_command(topology.primary, args.image)],
            json.dumps({"username": username, "token": token}),
        )
        token = ""
        if result.returncode:
            raise RuntimeError("Image cache operation failed; no activation was requested")
        receipt = json.loads(result.stdout)
        if receipt.get("image") != args.image or receipt.get("primary") != topology.primary.alias:
            raise RuntimeError("Image cache receipt differs from the reviewed target")
        if not all(receipt.get(key) is True for key in (
            "digest_verified", "deployment_lock_verified", "api_unchanged",
            "ephemeral_registry_config_removed",
        )):
            raise RuntimeError("Image cache verification is incomplete")
        print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
        print("Reviewed image caching failed; credentials and remote output withheld", file=sys.stderr)
        raise SystemExit(1) from None
