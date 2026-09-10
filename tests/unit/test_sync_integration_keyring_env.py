import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest
from dotenv import dotenv_values
from io import StringIO

from scripts.ha.sync_integration_keyring_env import render_env


def test_keyring_env_preserves_auth_and_literal_secret_characters():
    payload = {
        "active_key_id": "v1", "write_mode": "legacy",
        "keys": {"v1": "new-key" * 8},
        "legacy_secret_keys": ["old-${SECRET_KEY}-'quoted'-\\slash"],
    }
    current = "# settings\nSECRET_KEY=leave-this-alone\nSOME_FLAG=true\n"
    rendered = render_env(current, json.dumps(payload))
    result = dotenv_values(stream=StringIO(rendered), interpolate=False)
    assert result["SECRET_KEY"] == "leave-this-alone"
    assert result["SOME_FLAG"] == "true"
    assert json.loads(result["INTEGRATION_CREDENTIAL_KEYRING_JSON"]) == payload
    assert "# settings" in rendered
    assert render_env(rendered, json.dumps(payload)) == rendered


def test_keyring_env_rejects_ambiguous_duplicate_setting():
    payload = '{"active_key_id":"v1","write_mode":"active","keys":{"v1":"secret"},"legacy_secret_keys":[]}'
    with pytest.raises(ValueError, match="duplicate"):
        render_env("INTEGRATION_CREDENTIAL_KEYRING_JSON=a\nexport INTEGRATION_CREDENTIAL_KEYRING_JSON=b\n", payload)


def test_locked_env_update_is_atomic_and_rejects_stale_review(tmp_path):
    scripts = Path(__file__).resolve().parents[2] / "scripts" / "ha"
    helper = scripts / "safe_deploy_lock.py"
    env_file = tmp_path / ".env"
    original = b"SECRET_KEY=preserved-auth-key\nFLAG=kept\n"
    env_file.write_bytes(original)
    env_file.chmod(0o600)
    environment = os.environ.copy()
    environment["API_DEPLOY_LOCK_HELPER_SHA256"] = hashlib.sha256(helper.read_bytes()).hexdigest()
    command = [sys.executable, str(helper), "exec", str(tmp_path / ".deploy.lock"),
               sys.executable, str(scripts / "sync_integration_keyring_env.py"),
               "--env-file", str(env_file), "--expected-env-sha256", hashlib.sha256(original).hexdigest()]
    payload = json.dumps({"active_key_id": "v1", "write_mode": "active",
                          "keys": {"v1": "synthetic-master-key" * 3}, "legacy_secret_keys": []})
    first = subprocess.run(command, input=payload, text=True, capture_output=True, env=environment)
    assert first.returncode == 0, first.stderr
    updated = env_file.read_bytes()
    assert b"SECRET_KEY=preserved-auth-key\nFLAG=kept\n" in updated
    assert env_file.stat().st_mode & 0o777 == 0o600
    second = subprocess.run(command, input=payload, text=True, capture_output=True, env=environment)
    assert second.returncode == 1
    assert env_file.read_bytes() == updated
    assert "synthetic-master-key" not in first.stdout + second.stdout + second.stderr
    assert list(tmp_path.glob(".integration-keyring-*")) == []


def test_env_update_requires_deployment_lock(tmp_path):
    from scripts.ha.sync_integration_keyring_env import sync_env
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=preserved\n")
    with pytest.raises((ValueError, OSError)):
        sync_env(env_file, "{}", hashlib.sha256(env_file.read_bytes()).hexdigest())
