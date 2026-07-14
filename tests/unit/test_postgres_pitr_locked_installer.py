import json
import os
from pathlib import Path

import pytest

from scripts.ha import run_postgres_pitr_install_locked as locked


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts/ha/install_postgres_pitr_units.sh"


def test_locked_runner_passes_only_allowlisted_environment_and_live_fd(tmp_path):
    output = tmp_path / "result.json"
    installer = tmp_path / "installer.py"
    installer.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "for name in ('PITR_INSTALL_LOCK_FD', 'PITR_INSTALL_DEPLOY_LOCK_FD'):\n"
        "    os.fstat(int(os.environ[name]))\n"
        "payload = {'keys': sorted(os.environ), 'project': os.environ.get('PROJECT_DIR')}\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps(payload))\n",
        encoding="utf-8",
    )
    installer.chmod(0o700)
    lock_path = tmp_path / "shared.lock"

    result = locked.run_locked_install(
        installer,
        [str(output)],
        environ={
            "PROJECT_DIR": "/opt/air-api",
            "POSTGRES_PITR_S3_SECRET_ACCESS_KEY": "must-not-leak",
            "POSTGRES_IMAGE": "hostile:latest",
            "DB_SERVICE": "hostile-db",
            "PYTHONPATH": "/tmp/hostile",
        },
        expected_uid=os.geteuid(),
        lock_path=lock_path,
        deploy_lock_path=tmp_path / "deploy.lock",
    )

    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["project"] == "/opt/air-api"
    assert "POSTGRES_PITR_S3_SECRET_ACCESS_KEY" not in payload["keys"]
    assert "PYTHONPATH" not in payload["keys"]
    assert "POSTGRES_IMAGE" not in payload["keys"]
    assert "DB_SERVICE" not in payload["keys"]
    assert "DOCKER_CONTEXT" in payload["keys"]
    assert "PITR_INSTALL_LOCK_FD" in payload["keys"]
    assert "PITR_INSTALL_DEPLOY_LOCK_FD" in payload["keys"]


def test_shared_lock_is_nonblocking_and_rejects_symlink(tmp_path):
    lock_path = tmp_path / "shared.lock"
    descriptor = locked._open_lock(lock_path, expected_uid=os.geteuid())
    try:
        with pytest.raises(RuntimeError, match="another PITR host operation"):
            locked._open_lock(lock_path, expected_uid=os.geteuid())
    finally:
        os.close(descriptor)

    target = tmp_path / "target.lock"
    target.touch()
    linked = tmp_path / "linked.lock"
    linked.symlink_to(target)
    with pytest.raises(OSError):
        locked._open_lock(linked, expected_uid=os.geteuid())


def test_installer_cannot_bypass_lock_and_leaves_host_state_to_transaction():
    source = INSTALLER.read_text(encoding="utf-8")
    assert "PITR_INSTALL_LOCK_HELD" not in source
    assert "PITR_INSTALL_LOCK_FD" in source
    assert "/proc/self/fd/${PITR_INSTALL_LOCK_FD}" in source
    assert "/run/lock/mvn-postgres-pitr-prerequisites.lock" in source
    assert "flock -n" in source
    assert "mktemp /etc/.mvn-postgres-pitr.env." not in source
    assert "docker run --pull never --rm" not in source
    assert "/var/lib/mvn-postgres-pitr/basebackups" not in source
    assert "mvn-postgres-pitr-provision-host" in source
    assert "Host state was not provisioned" in source
    assert 'DB_SERVICE="db"' in source
    assert "mvn-postgres-wal-upload.service" in source
    assert "mvn-postgres-basebackup.service" in source
    assert "mvn-patroni-role-agent.service must be inactive" in source
    assert 'systemctl is-active "${unit}"' in source
    assert 'systemctl is-enabled "${timer}"' in source
    assert "must be disabled before PITR host asset installation" in source
    assert source.rindex("systemctl daemon-reload") > source.rindex(
        "install -o root -g root"
    )
    assert source.count("require_install_quiescence") == 3
