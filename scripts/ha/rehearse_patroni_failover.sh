#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${PATRONI_REHEARSAL_COMPOSE_FILE:-deploy/ha/patroni/rehearsal/docker-compose.yml}"
KEEP="${PATRONI_REHEARSAL_KEEP:-false}"
TIMEOUT="${PATRONI_REHEARSAL_TIMEOUT:-120}"
IMAGE="${PATRONI_REHEARSAL_IMAGE:-}"
BUILD_LOCAL="${PATRONI_REHEARSAL_BUILD_LOCAL:-false}"
COMPOSE=(docker compose -f "${COMPOSE_FILE}")
PULLED_IMAGE_ID=""

log() {
  printf '[patroni-rehearsal][%s] %s\n' "$1" "$2"
}

cleanup() {
  if [[ "${KEEP}" != "true" ]]; then
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

role() {
  local service="$1"
  "${COMPOSE[@]}" exec -T "${service}" \
    python3 -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8008/patroni", timeout=3))["role"])' \
    2>/dev/null || true
}

wait_for_roles() {
  local expected_leaders="$1"
  local expected_replicas="$2"
  local deadline=$((SECONDS + TIMEOUT))
  while (( SECONDS < deadline )); do
    local pg1_role pg2_role leaders=0 replicas=0
    pg1_role="$(role pg1)"
    pg2_role="$(role pg2)"
    [[ "${pg1_role}" == "primary" || "${pg1_role}" == "leader" ]] && leaders=$((leaders + 1))
    [[ "${pg2_role}" == "primary" || "${pg2_role}" == "leader" ]] && leaders=$((leaders + 1))
    [[ "${pg1_role}" == "replica" ]] && replicas=$((replicas + 1))
    [[ "${pg2_role}" == "replica" ]] && replicas=$((replicas + 1))
    if [[ "${leaders}" == "${expected_leaders}" && "${replicas}" == "${expected_replicas}" ]]; then
      printf '%s|%s\n' "${pg1_role}" "${pg2_role}"
      return 0
    fi
    sleep 2
  done
  "${COMPOSE[@]}" ps
  "${COMPOSE[@]}" logs --tail=120 pg1 pg2
  return 1
}

leader_service() {
  if [[ "$(role pg1)" == "primary" || "$(role pg1)" == "leader" ]]; then
    echo pg1
  elif [[ "$(role pg2)" == "primary" || "$(role pg2)" == "leader" ]]; then
    echo pg2
  else
    return 1
  fi
}

other_service() {
  [[ "$1" == "pg1" ]] && echo pg2 || echo pg1
}

sql() {
  local service="$1"
  local statement="$2"
  "${COMPOSE[@]}" exec -T \
    -e "PGOPTIONS=-c statement_timeout=10000" \
    "${service}" \
    psql -U postgres -d postgres -v ON_ERROR_STOP=1 -Atqc "${statement}"
}

prepare_images() {
  local docker_architecture=""
  local pulled_platform=""
  if [[ -n "${IMAGE}" ]]; then
    [[ "${BUILD_LOCAL}" == "false" ]] || {
      log error "exact-image and local-build modes are mutually exclusive"
      return 1
    }
    [[ "${IMAGE}" =~ ^ghcr\.io/mvnby/air-api/patroni@sha256:[0-9a-f]{64}$ ]] || {
      log error "PATRONI_REHEARSAL_IMAGE must be the immutable MVN Patroni image"
      return 1
    }
    export PATRONI_REHEARSAL_PLATFORM=linux/amd64
    log start "pulling exact linux/amd64 Patroni image ${IMAGE}"
    docker pull --platform linux/amd64 "${IMAGE}"
    PULLED_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE}")"
    pulled_platform="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "${IMAGE}")"
    [[ "${PULLED_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]] || {
      log error "could not resolve the pulled image ID"
      return 1
    }
    [[ "${pulled_platform}" == "linux/amd64" ]] || {
      log error "pulled image platform ${pulled_platform} is not linux/amd64"
      return 1
    }
    "${COMPOSE[@]}" pull etcd1 etcd2 etcd3
    return 0
  fi

  [[ "${BUILD_LOCAL}" == "true" ]] || {
    log error "set an immutable PATRONI_REHEARSAL_IMAGE or explicitly opt into PATRONI_REHEARSAL_BUILD_LOCAL=true"
    return 1
  }
  if [[ -z "${PATRONI_REHEARSAL_PLATFORM:-}" ]]; then
    docker_architecture="$(docker info --format '{{.Architecture}}')"
    PATRONI_REHEARSAL_PLATFORM="linux/${docker_architecture}"
    export PATRONI_REHEARSAL_PLATFORM
  fi
  log start "building source-only local Patroni rehearsal image"
  "${COMPOSE[@]}" build pg1
}

start_cluster() {
  if [[ -n "${IMAGE}" ]]; then
    log start "starting exact image with builds and implicit pulls disabled"
    "${COMPOSE[@]}" up -d --wait --no-build --pull never
  else
    log start "starting source-only local rehearsal cluster"
    "${COMPOSE[@]}" up -d --wait
  fi
}

verify_running_image_ids() {
  [[ -n "${IMAGE}" ]] || return 0
  local service container_id running_image_id
  for service in pg1 pg2; do
    container_id="$("${COMPOSE[@]}" ps -q "${service}")"
    [[ -n "${container_id}" ]] || {
      log error "${service} has no running container"
      return 1
    }
    running_image_id="$(docker inspect --format '{{.Image}}' "${container_id}")"
    if [[ "${running_image_id}" != "${PULLED_IMAGE_ID}" ]]; then
      log error "${service} image ID ${running_image_id} differs from pulled ${PULLED_IMAGE_ID}"
      return 1
    fi
  done
  log check "both Patroni containers use pulled image ID ${PULLED_IMAGE_ID}"
}

archive_helper_probe() {
  local service="pg1"
  "${COMPOSE[@]}" exec -T --user root "${service}" sh -euc '
    install -d -o postgres -g postgres -m 0700 /postgres-wal-archive /tmp/mvn-wal-source
    rm -f /postgres-wal-archive/0000000A.history /tmp/mvn-wal-source/0000000A.history
  '
  # The single-quoted program is intentionally expanded only inside the container.
  # shellcheck disable=SC2016
  "${COMPOSE[@]}" exec -T --user postgres "${service}" sh -euc '
    umask 077
    source=/tmp/mvn-wal-source/0000000A.history
    printf "release-rehearsal\n" > "${source}"
    mvn-patroni-archive-wal "${source}" 0000000A.history
    mvn-patroni-archive-wal "${source}" 0000000A.history
    cmp "${source}" /postgres-wal-archive/0000000A.history
    printf "collision\n" > "${source}"
    if mvn-patroni-archive-wal "${source}" 0000000A.history >/tmp/collision.out 2>&1; then
      echo "archive helper accepted a different-content collision" >&2
      exit 1
    fi
    grep -F "destination differs" /tmp/collision.out >/dev/null
    printf "release-rehearsal\n" | cmp - /postgres-wal-archive/0000000A.history
  '

  if grep -F '.partial' deploy/ha/patroni/archive_wal.py >/dev/null; then
    "${COMPOSE[@]}" exec -T --user root "${service}" sh -euc '
      rm -f /postgres-wal-archive/00000001000000000000000A.partial \
        /tmp/mvn-wal-source/00000001000000000000000A.partial
    '
    # The single-quoted program is intentionally expanded only inside the container.
    # shellcheck disable=SC2016
    "${COMPOSE[@]}" exec -T --user postgres "${service}" sh -euc '
      umask 077
      source=/tmp/mvn-wal-source/00000001000000000000000A.partial
      dd if=/dev/zero of="${source}" bs=1M count=16 status=none
      mvn-patroni-archive-wal "${source}" "$(basename "${source}")"
      mvn-patroni-archive-wal "${source}" "$(basename "${source}")"
      test "$(wc -c < /postgres-wal-archive/$(basename "${source}"))" = 16777216
    '
    log check "archive helper accepted an exact 16 MiB .partial WAL idempotently"
  else
    log check "archive helper source does not yet advertise .partial support; partial probe skipped"
  fi
  log check "archive helper is idempotent and rejects different-content collisions"
}

[[ "${TIMEOUT}" =~ ^[1-9][0-9]*$ ]] || {
  log error "PATRONI_REHEARSAL_TIMEOUT must be a positive integer"
  exit 1
}
command -v docker >/dev/null 2>&1 || {
  log error "docker is required"
  exit 1
}

prepare_images
start_cluster
verify_running_image_ids
wait_for_roles 1 1 >/dev/null
archive_helper_probe

leader="$(leader_service)"
replica="$(other_service "${leader}")"
log check "initial leader=${leader} replica=${replica}"
sql "${leader}" "create table if not exists ha_rehearsal (id integer primary key, value text not null); insert into ha_rehearsal values (1, 'before-failover') on conflict (id) do update set value=excluded.value;"

deadline=$((SECONDS + TIMEOUT))
until [[ "$(sql "${replica}" "select value from ha_rehearsal where id=1" 2>/dev/null || true)" == "before-failover" ]]; do
  (( SECONDS < deadline )) || {
    log error "replica did not receive the rehearsal row"
    exit 1
  }
  sleep 2
done

deadline=$((SECONDS + TIMEOUT))
until [[ "$(sql "${leader}" "select sync_state from pg_stat_replication where application_name='${replica}' and state='streaming'" 2>/dev/null || true)" == "sync" ]]; do
  (( SECONDS < deadline )) || {
    log error "replica was not registered as synchronous"
    exit 1
  }
  sleep 2
done
deadline=$((SECONDS + TIMEOUT))
until "${COMPOSE[@]}" exec -T "${replica}" \
  curl -fsS http://127.0.0.1:8008/sync >/dev/null 2>&1; do
  (( SECONDS < deadline )) || {
    log error "Patroni did not publish ${replica} as the failover-safe synchronous standby"
    exit 1
  }
  sleep 2
done
log check "DCS-confirmed synchronous standby=${replica}"

log failover "stopping leader ${leader}"
"${COMPOSE[@]}" stop "${leader}"
deadline=$((SECONDS + TIMEOUT))
until [[ "$(role "${replica}")" == "primary" || "$(role "${replica}")" == "leader" ]]; do
  (( SECONDS < deadline )) || {
    log error "replica was not promoted"
    exit 1
  }
  sleep 2
done
sql "${replica}" "select value from ha_rehearsal where id=1" | grep -Fx before-failover >/dev/null
sql "${replica}" "insert into ha_rehearsal values (2, 'after-failover');"

log rejoin "starting former leader ${leader}"
"${COMPOSE[@]}" up -d "${leader}"
wait_for_roles 1 1 >/dev/null
deadline=$((SECONDS + TIMEOUT))
until [[ "$(sql "${leader}" "select value from ha_rehearsal where id=2" 2>/dev/null || true)" == "after-failover" ]]; do
  (( SECONDS < deadline )) || {
    log error "former leader did not rejoin with the new timeline"
    exit 1
  }
  sleep 2
done

log quorum "stopping one etcd member"
"${COMPOSE[@]}" stop etcd3
sleep 8
[[ -n "$(leader_service)" ]] || {
  log error "Patroni lost its leader after one etcd member stopped"
  exit 1
}

if [[ -n "${IMAGE}" ]]; then
  log "done" "exact-image identity, archive helper, failover, data continuity, rejoin, and quorum passed"
else
  log "done" "source-only archive helper, failover, data continuity, rejoin, and quorum passed; release_evidence=false"
fi
