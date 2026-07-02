#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/mvn-reserve}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.reserve.yml}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:18000/api/health}"
LOCAL_READY_URL="${LOCAL_READY_URL:-http://127.0.0.1:18000/api/ready}"

cd "${PROJECT_DIR}"
COMPOSE=(docker compose -f "${COMPOSE_FILE}")

printf 'containers:\n'
"${COMPOSE[@]}" ps

printf '\npostgres:\n'
"${COMPOSE[@]}" exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -v ON_ERROR_STOP=1' <<'SQL'
SELECT pg_is_in_recovery() AS in_recovery, pg_last_wal_receive_lsn() AS receive_lsn, pg_last_wal_replay_lsn() AS replay_lsn;
SELECT status, sender_host, sender_port, slot_name, latest_end_lsn FROM pg_stat_wal_receiver;
SQL

printf '\napi:\n'
printf 'health_status='
curl -s -o /tmp/mvn-health.out -w '%{http_code}' "${LOCAL_HEALTH_URL}"
printf ' body='
cat /tmp/mvn-health.out
printf '\n'
printf 'ready_status='
curl -s -o /tmp/mvn-ready.out -w '%{http_code}' "${LOCAL_READY_URL}"
printf ' body='
cat /tmp/mvn-ready.out
printf '\n'

printf '\nmedia timer:\n'
systemctl is-active mvn-media-sync.timer || true
systemctl list-timers --all | grep mvn-media-sync || true
