#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:15-alpine}"
ENABLE_TIMERS="${ENABLE_TIMERS:-false}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the current PostgreSQL primary host." >&2
  exit 1
fi

if [[ ! -f "scripts/ha/upload_postgres_pitr_to_s3.py" ]]; then
  echo "Run from the air-api repository root, or copy scripts/ha first." >&2
  exit 1
fi

install -m 0755 scripts/ha/upload_postgres_pitr_to_s3.py /usr/local/sbin/mvn-postgres-pitr-upload
install -m 0755 scripts/ha/upload_postgres_pitr_wal.sh /usr/local/sbin/mvn-postgres-pitr-upload-wal
install -m 0755 scripts/ha/create_postgres_pitr_basebackup.sh /usr/local/sbin/mvn-postgres-pitr-basebackup
install -m 0644 deploy/ha/systemd/mvn-postgres-wal-upload.service /etc/systemd/system/mvn-postgres-wal-upload.service
install -m 0644 deploy/ha/systemd/mvn-postgres-wal-upload.timer /etc/systemd/system/mvn-postgres-wal-upload.timer
install -m 0644 deploy/ha/systemd/mvn-postgres-basebackup.service /etc/systemd/system/mvn-postgres-basebackup.service
install -m 0644 deploy/ha/systemd/mvn-postgres-basebackup.timer /etc/systemd/system/mvn-postgres-basebackup.timer

archive_dir="${PROJECT_DIR}/postgres-wal-archive"
mkdir -p "${archive_dir}"
postgres_owner="$(docker run --rm "${POSTGRES_IMAGE}" sh -lc 'printf "%s:%s" "$(id -u postgres)" "$(id -g postgres)"')"
chown "${postgres_owner}" "${archive_dir}"
chmod 700 "${archive_dir}"
{
  printf 'PROJECT_DIR=%q\n' "${PROJECT_DIR}"
  printf 'COMPOSE_FILE=%q\n' "${COMPOSE_FILE}"
} >/etc/mvn-postgres-pitr.env
chmod 600 /etc/mvn-postgres-pitr.env

systemctl daemon-reload

if [[ "${ENABLE_TIMERS}" == "true" ]]; then
  systemctl enable --now mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer
else
  echo "Installed PITR units. Timers are not enabled yet."
  echo "After POSTGRES_PITR_* env and archive_mode are active, run:"
  echo "  systemctl enable --now mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer"
fi
