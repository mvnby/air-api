#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${ETCD_CONTAINER:-mvn-etcd}"
MAX_RAFT_LAG="${ETCD_MAX_RAFT_LAG:-100}"
EXPECTED_MEMBERS="${ETCD_EXPECTED_MEMBERS:-3}"
ENDPOINTS="${ETCD_ENDPOINTS:-https://10.77.0.2:2379,https://10.77.0.1:2379,https://10.77.0.3:2379}"
PKI_DIR="${ETCD_PKI_DIR:-/etc/etcd/pki}"

log() {
  printf '[etcd-quorum][%s] %s\n' "$1" "$2"
}

for value in "${MAX_RAFT_LAG}" "${EXPECTED_MEMBERS}"; do
  [[ "${value}" =~ ^[0-9]+$ ]] || {
    log error "member and lag limits must be unsigned integers"
    exit 1
  }
done
docker inspect "${CONTAINER}" >/dev/null 2>&1 || {
  log error "container is missing: ${CONTAINER}"
  exit 1
}

status_json="$({
  docker exec \
    "${CONTAINER}" \
    etcdctl \
    --endpoints="${ENDPOINTS}" \
    --cacert="${PKI_DIR}/ca.crt" \
    --cert="${PKI_DIR}/node.crt" \
    --key="${PKI_DIR}/node.key" \
    endpoint status --cluster --write-out=json
} 2>/dev/null)"

python3 - "${EXPECTED_MEMBERS}" "${MAX_RAFT_LAG}" "${status_json}" <<'PY'
import json
import sys

expected_members = int(sys.argv[1])
max_raft_lag = int(sys.argv[2])
payload = json.loads(sys.argv[3])
if len(payload) != expected_members:
    raise SystemExit(f"expected {expected_members} etcd members, got {len(payload)}")

headers = [entry.get("Status", {}).get("header", {}) for entry in payload]
cluster_ids = {header.get("cluster_id") for header in headers}
if len(cluster_ids) != 1 or None in cluster_ids:
    raise SystemExit(f"members disagree on cluster id: {cluster_ids}")

leaders = {entry.get("Status", {}).get("leader") for entry in payload}
if len(leaders) != 1 or 0 in leaders or None in leaders:
    raise SystemExit(f"members disagree on leader: {leaders}")

indexes = [int(entry.get("Status", {}).get("raftIndex", 0)) for entry in payload]
if not all(indexes):
    raise SystemExit(f"invalid raft indexes: {indexes}")
lag = max(indexes) - min(indexes)
if lag > max_raft_lag:
    raise SystemExit(f"raft index lag {lag} exceeds {max_raft_lag}")

versions = sorted({entry.get("Status", {}).get("version", "") for entry in payload})
print(
    "etcd_quorum_status=passed "
    f"members={len(payload)} leader={next(iter(leaders))} "
    f"raft_lag={lag} versions={','.join(versions)}"
)
PY

docker exec \
  "${CONTAINER}" \
  etcdctl \
  --endpoints="${ENDPOINTS}" \
  --cacert="${PKI_DIR}/ca.crt" \
  --cert="${PKI_DIR}/node.crt" \
  --key="${PKI_DIR}/node.key" \
  endpoint health --cluster >/dev/null

log "done" "all ${EXPECTED_MEMBERS} members are healthy"
