import os
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "deploy/ha/quorum/docker-compose.etcd.yml"
UNIT = REPO_ROOT / "deploy/ha/quorum/mvn-etcd-quorum.service"
GENERATE = REPO_ROOT / "scripts/ha/generate_etcd_pki.sh"
CHECK = REPO_ROOT / "scripts/ha/check_etcd_quorum.sh"


def _executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_etcd_compose_is_three_member_tls_only_and_digest_pinned():
    payload = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    service = payload["services"]["etcd"]
    text = COMPOSE.read_text(encoding="utf-8")

    assert "@sha256:" in service["image"]
    assert service["network_mode"] == "host"
    assert "http://" not in text
    assert "--client-cert-auth=true" in service["command"]
    assert "--peer-client-cert-auth=true" in service["command"]
    assert "mvn-api=https://10.77.0.2:2380" in text
    assert "zakup=https://10.77.0.1:2380" in text
    assert "mvn-web=https://10.77.0.3:2380" in text
    assert service["mem_limit"] == "${ETCD_MEMORY_LIMIT:-192m}"
    assert service["logging"]["options"]["max-file"] == "5"
    assert service["healthcheck"]["test"][0] == "CMD"
    assert service["healthcheck"]["test"][1] == "/usr/local/bin/etcdctl"
    assert "CMD-SHELL" not in service["healthcheck"]["test"]
    assert "ETCDCTL_API" not in text


def test_etcd_systemd_unit_waits_for_wireguard_and_docker():
    text = UNIT.read_text(encoding="utf-8")

    assert "Requires=docker.service wg-quick@wg-mvn.service" in text
    assert "ConditionPathExists=/opt/mvn-quorum/pki/node.key" in text
    assert "docker compose --env-file .env -f docker-compose.etcd.yml up -d --wait" in text


def test_pki_generator_creates_distinct_valid_certificates(tmp_path):
    output = tmp_path / "pki"
    env = os.environ.copy()
    env["ETCD_PKI_OUTPUT_DIR"] = str(output)

    result = subprocess.run(["bash", str(GENERATE)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    ca_text = subprocess.run(
        ["openssl", "x509", "-in", str(output / "ca.crt"), "-noout", "-text"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert "X509v3 Basic Constraints: critical" in ca_text
    assert "CA:TRUE" in ca_text
    assert "X509v3 Key Usage: critical" in ca_text
    assert "Certificate Sign, CRL Sign" in ca_text
    for node in ("mvn-api", "zakup", "mvn-web"):
        node_dir = output / "nodes" / node
        assert (node_dir / "ca.crt").is_file()
        assert (node_dir / "node.crt").is_file()
        assert (node_dir / "node.key").stat().st_mode & 0o777 == 0o600
        verify = subprocess.run(
            ["openssl", "verify", "-CAfile", str(output / "ca.crt"), str(node_dir / "node.crt")],
            text=True,
            capture_output=True,
            check=False,
        )
        assert verify.returncode == 0, verify.stderr
    assert (output / "operator/operator.crt").is_file()
    assert (output / "operator/operator.key").is_file()
    assert (output / "ca-private/ca.key").is_file()

    duplicate = subprocess.run(
        ["bash", str(GENERATE)], env=env, text=True, capture_output=True, check=False
    )
    assert duplicate.returncode == 1
    assert "refusing to replace" in duplicate.stdout


def test_quorum_check_requires_three_members_and_one_leader():
    text = CHECK.read_text(encoding="utf-8")

    assert "ETCD_EXPECTED_MEMBERS:-3" in text
    assert "members disagree on leader" in text
    assert "raft index lag" in text
    assert "endpoint health --cluster" in text
    assert "ETCDCTL_API" not in text


def test_quorum_check_accepts_consistent_healthy_cluster(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
if [[ "$1" == "inspect" ]]; then
  exit 0
fi
if [[ "$*" == *"endpoint status"* ]]; then
  cat <<'JSON'
[
  {"Endpoint":"https://10.77.0.1:2379","Status":{"header":{"cluster_id":7},"version":"3.6.11","leader":11,"raftIndex":100}},
  {"Endpoint":"https://10.77.0.2:2379","Status":{"header":{"cluster_id":7},"version":"3.6.11","leader":11,"raftIndex":101}},
  {"Endpoint":"https://10.77.0.3:2379","Status":{"header":{"cluster_id":7},"version":"3.6.11","leader":11,"raftIndex":101}}
]
JSON
  exit 0
fi
if [[ "$*" == *"endpoint health"* ]]; then
  exit 0
fi
exit 1
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = subprocess.run(["bash", str(CHECK)], env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert "etcd_quorum_status=passed members=3" in result.stdout
    assert "raft_lag=1" in result.stdout
