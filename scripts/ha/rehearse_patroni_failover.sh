#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${PATRONI_REHEARSAL_COMPOSE_FILE:-deploy/ha/patroni/rehearsal/docker-compose.yml}"
KEEP="${PATRONI_REHEARSAL_KEEP:-false}"
TIMEOUT="${PATRONI_REHEARSAL_TIMEOUT:-120}"
COMPOSE=(docker compose -f "${COMPOSE_FILE}")

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

[[ "${TIMEOUT}" =~ ^[1-9][0-9]*$ ]] || {
  log error "PATRONI_REHEARSAL_TIMEOUT must be a positive integer"
  exit 1
}
command -v docker >/dev/null 2>&1 || {
  log error "docker is required"
  exit 1
}

log start "building isolated Patroni image"
"${COMPOSE[@]}" build pg1
log start "starting three etcd members and two PostgreSQL nodes"
"${COMPOSE[@]}" up -d --wait
wait_for_roles 1 1 >/dev/null

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
log check "synchronous standby=${replica}"

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

log "done" "automatic failover, data continuity, rejoin, and one-member quorum loss passed"
