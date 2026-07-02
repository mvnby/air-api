#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
LOCAL_READY_URL="${LOCAL_READY_URL:-http://127.0.0.1:8000/api/ready}"

cd "${PROJECT_DIR}"
COMPOSE=(docker compose -f "${COMPOSE_FILE}")

echo "containers:"
"${COMPOSE[@]}" ps

echo
echo "api_ready:"
curl -fsS "${LOCAL_READY_URL}" || true
printf '\n'

echo
echo "runtime:"
"${COMPOSE[@]}" exec -T app python - <<'PY'
from core.config import settings

print("APP_ROLE", settings.APP_ROLE)
print("API_READY", settings.api_ready_control_decision)
print("SCHEDULER", settings.scheduler_control_decision)
print("BOT_IN_APP", settings.bot_control_decision)
print("MAIL_IMAP_AUTO_IMPORT_ENABLED", settings.MAIL_IMAP_AUTO_IMPORT_ENABLED)
print("MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED", settings.MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED)
PY

echo
echo "bot_runtime:"
"${COMPOSE[@]}" exec -T bot python - <<'PY'
from core.config import settings

print("APP_ROLE", settings.APP_ROLE)
print("BOT", settings.bot_control_decision)
print("SCHEDULER", settings.scheduler_control_decision)
PY

echo
echo "postgres_primary_and_replication:"
"${COMPOSE[@]}" exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -v ON_ERROR_STOP=1' <<'SQL'
SELECT pg_is_in_recovery() AS in_recovery, pg_current_wal_lsn() AS current_lsn;
SELECT slot_name, active, active_pid, restart_lsn FROM pg_replication_slots;
SELECT application_name, client_addr, state, sync_state, replay_lsn FROM pg_stat_replication;
SELECT name, setting FROM pg_settings WHERE name IN ('archive_mode', 'archive_timeout', 'archive_command') ORDER BY name;
SELECT archived_count, last_archived_wal, last_archived_time, failed_count, last_failed_wal, last_failed_time FROM pg_stat_archiver;
SELECT locktype, granted, objid::bigint, pid, mode FROM pg_locks WHERE locktype = 'advisory' ORDER BY pid;
SQL

echo
echo "pitr_timers:"
systemctl is-active mvn-postgres-wal-upload.timer || true
systemctl is-active mvn-postgres-basebackup.timer || true
systemctl list-timers --all | grep mvn-postgres || true
if command -v mvn-postgres-pitr-status >/dev/null 2>&1; then
  echo
  echo "pitr_status:"
  PITR_REQUIRED="${PITR_REQUIRED:-false}" mvn-postgres-pitr-status || true
fi

echo
echo "backups:"
"${COMPOSE[@]}" exec -T app python - <<'PY'
from datetime import datetime, timezone
from services.backup_service import backup_service

items = backup_service.list_backups(limit=20)
now = datetime.now(timezone.utc)
for kind in ("db", "media"):
    latest = next((item for item in items if item.get("kind") == kind), None)
    if not latest:
        print(kind, "missing")
        continue
    created = latest.get("created_at")
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = (now - created).total_seconds() / 3600 if created else -1
    print(kind, f"age_hours={age:.1f}", latest.get("name"), created)
PY
