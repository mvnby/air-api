"""Fixed cache-only operation, embedded by cache_api_image.py under deploy lock."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def docker(*arguments, **kwargs):
    result = subprocess.run(
        ["docker", *arguments], text=True, capture_output=True, timeout=180, **kwargs,
    )
    require(result.returncode == 0, "Docker image cache step failed")
    return result.stdout


def endpoint(path):
    with urllib.request.urlopen("http://127.0.0.1:" + path, timeout=10) as response:
        require(response.status == 200, "Primary is not ready")
        return json.load(response)


def active_api(project_dir):
    slot = (Path(project_dir) / ".active-api-slot").read_text().strip()
    require(slot in {"blue", "green"}, "Unknown active API slot")
    project = "air-api" if project_dir == "/opt/air-api" else "mvn_reserve"
    ids = docker("ps", "-q", "--filter", "label=com.docker.compose.project=" + project,
                 "--filter", "label=com.docker.compose.service=app-" + slot).split()
    require(len(ids) == 1, "Active API container is ambiguous")
    container = json.loads(docker("inspect", ids[0]))[0]
    require(container["State"]["Running"], "Active API is stopped")
    return slot, ids[0], container["Config"]["Image"]


def cache_image(project_dir, image_reference):
    require(project_dir in {"/opt/air-api", "/opt/mvn-reserve"}, "Unreviewed project")
    require(re.fullmatch(r"ghcr\.io/mvnby/air-api/backend@sha256:[0-9a-f]{64}", image_reference), "Invalid image")
    require(os.environ.get("API_DEPLOY_LOCK_FD") == "9", "Deployment lock is absent")
    subprocess.run(
        [sys.executable, "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py", "verify",
         project_dir + "/.deploy.lock", "9"], check=True, pass_fds=(9,), capture_output=True,
    )
    for marker in ("/run/mvn-postgres-pitr-maintenance", project_dir + "/.patroni-cutover-in-progress"):
        require(not Path(marker).exists(), "Production maintenance is active")
    patroni = endpoint("8008/patroni")
    require(patroni.get("state") == "running" and patroni.get("role") in {"primary", "master", "leader"}, "Node is not primary")
    require(endpoint("18080/api/ready").get("status") == "ok", "API is not ready")
    before = active_api(project_dir)
    credential = json.loads(sys.stdin.read(16385))
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", credential.get("username", "")), "Invalid registry username")
    token = credential.get("token", "")
    require(isinstance(token, str) and 0 < len(token) <= 8192 and not any(c.isspace() for c in token), "Invalid registry token")
    with tempfile.TemporaryDirectory(prefix="mvn-api-image-registry-", dir="/run") as directory:
        environment = os.environ.copy()
        environment["DOCKER_CONFIG"] = directory
        docker("login", "ghcr.io", "--username", credential["username"], "--password-stdin", input=token, env=environment)
        credential.clear()
        token = ""
        docker("pull", image_reference, env=environment)
        image = json.loads(docker("image", "inspect", image_reference, env=environment))[0]
        require(image_reference in image.get("RepoDigests", []) and image.get("Os") == "linux", "Image digest does not match")
    require(not Path(directory).exists(), "Temporary registry credentials remain")
    require(active_api(project_dir) == before, "Active API changed while caching")
    require(endpoint("8008/patroni").get("role") in {"primary", "master", "leader"}, "Primary changed while caching")
    require(endpoint("18080/api/ready").get("status") == "ok", "API is not ready after caching")
    print(json.dumps({
        "image": image_reference, "primary": patroni["patroni"]["name"], "digest_verified": True,
        "deployment_lock_verified": True, "api_unchanged": True,
        "ephemeral_registry_config_removed": True,
    }))
