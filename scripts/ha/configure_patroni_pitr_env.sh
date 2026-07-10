#!/usr/bin/env bash
set -euo pipefail

APP_ENV_FILE="${PATRONI_APP_ENV_FILE:?set PATRONI_APP_ENV_FILE}"
PITR_ENV_FILE="${PATRONI_SYSTEMD_ENV_FILE:-/etc/mvn-postgres-pitr.env}"
PROJECT_DIR="${PATRONI_PROJECT_DIR:?set PATRONI_PROJECT_DIR}"
COMPOSE_FILE="${PATRONI_COMPOSE_FILE:-docker-compose.patroni.yml}"

payload="$(mktemp)"
temporary=""
trap 'rm -f "${payload}" "${temporary}"' EXIT

while IFS= read -r line; do
  [[ -n "${line}" ]] || continue
  key="${line%%=*}"
  [[ "${line}" == *=* && "${key}" =~ ^POSTGRES_PITR_(ARCHIVE_MODE|ARCHIVE_TIMEOUT|CLUSTER|S3_[A-Z0-9_]+)$ ]] || {
    echo "unsupported PITR env key: ${key}" >&2
    exit 1
  }
  printf '%s\n' "${line}" >> "${payload}"
done

for required in \
  POSTGRES_PITR_S3_ACCESS_KEY_ID \
  POSTGRES_PITR_S3_SECRET_ACCESS_KEY \
  POSTGRES_PITR_S3_BUCKET \
  POSTGRES_PITR_S3_ENDPOINT_URL; do
  grep -q "^${required}=" "${payload}" || {
    echo "required PITR env key is missing: ${required}" >&2
    exit 1
  }
done
[[ -f "${APP_ENV_FILE}" ]] || {
  echo "app env file is missing: ${APP_ENV_FILE}" >&2
  exit 1
}

backup="${APP_ENV_FILE}.bak-patroni-pitr-$(date -u +%Y%m%dT%H%M%SZ)"
cp -a "${APP_ENV_FILE}" "${backup}"
temporary="$(mktemp "${APP_ENV_FILE}.tmp.XXXXXX")"
grep -vE '^POSTGRES_PITR_(ARCHIVE_MODE|ARCHIVE_TIMEOUT|CLUSTER|S3_[A-Z0-9_]+)=' \
  "${APP_ENV_FILE}" > "${temporary}" || true
cat "${payload}" >> "${temporary}"
if ! chmod --reference="${APP_ENV_FILE}" "${temporary}" 2>/dev/null; then
  mode="$(stat -c '%a' "${APP_ENV_FILE}" 2>/dev/null || stat -f '%Lp' "${APP_ENV_FILE}")"
  chmod "${mode}" "${temporary}"
fi
chown --reference="${APP_ENV_FILE}" "${temporary}" 2>/dev/null || true
mv "${temporary}" "${APP_ENV_FILE}"
temporary=""

install -d -m 0755 "$(dirname "${PITR_ENV_FILE}")"
if [[ -f "${PITR_ENV_FILE}" ]]; then
  cp -a "${PITR_ENV_FILE}" "${PITR_ENV_FILE}.bak-patroni-$(date -u +%Y%m%dT%H%M%SZ)"
fi
temporary="$(mktemp "${PITR_ENV_FILE}.tmp.XXXXXX")"
printf 'PROJECT_DIR=%s\nCOMPOSE_FILE=%s\n' "${PROJECT_DIR}" "${COMPOSE_FILE}" > "${temporary}"
chmod 0600 "${temporary}"
mv "${temporary}" "${PITR_ENV_FILE}"
temporary=""

echo "patroni_pitr_env=prepared app_backup=${backup}"
