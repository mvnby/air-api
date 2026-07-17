#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/mvn-reserve}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.reserve.yml}"
PRIMARY_COMPOSE_FILE="${PRIMARY_COMPOSE_FILE:-docker-compose.primary.yml}"
LOCAL_READY_URL="${LOCAL_READY_URL:-http://127.0.0.1:18000/api/ready}"
OLD_PRIMARY_SSH="${OLD_PRIMARY_SSH:-}"
OLD_PRIMARY_PROJECT_DIR="${OLD_PRIMARY_PROJECT_DIR:-/opt/air-api}"
OLD_PRIMARY_COMPOSE_FILE="${OLD_PRIMARY_COMPOSE_FILE:-docker-compose.prod.yml}"
CONFIRM_PROMOTE="${CONFIRM_PROMOTE:-false}"
ALLOW_UNFENCED_PROMOTE="${ALLOW_UNFENCED_PROMOTE:-false}"

usage() {
  cat <<'USAGE'
Usage:
  CONFIRM_PROMOTE=true bash scripts/ha/promote_local_standby.sh
  CONFIRM_PROMOTE=true bash scripts/ha/promote_local_standby.sh --allow-unfenced

Runs on the standby host. It fences the old primary when OLD_PRIMARY_SSH is set,
promotes local PostgreSQL, swaps the local compose file to the prepared primary
compose, starts the API app, disables media pull, and verifies local /api/ready.

By default the helper refuses to promote when OLD_PRIMARY_SSH is empty. If the
old primary is unreachable and cannot be fenced over SSH, explicitly set
ALLOW_UNFENCED_PROMOTE=true or pass --allow-unfenced.

Important env:
  PROJECT_DIR=/opt/mvn-reserve
  COMPOSE_FILE=docker-compose.reserve.yml
  PRIMARY_COMPOSE_FILE=docker-compose.primary.yml
  OLD_PRIMARY_SSH=root@10.77.0.2
  OLD_PRIMARY_PROJECT_DIR=/opt/air-api
  OLD_PRIMARY_COMPOSE_FILE=docker-compose.prod.yml
  LOCAL_READY_URL=http://127.0.0.1:18000/api/ready
  CONFIRM_PROMOTE=true
  ALLOW_UNFENCED_PROMOTE=false
USAGE
}

for arg in "$@"; do
  case "${arg}" in
    -h|--help)
      usage
      exit 0
      ;;
    --yes)
      CONFIRM_PROMOTE=true
      ;;
    --allow-unfenced)
      ALLOW_UNFENCED_PROMOTE=true
      ;;
    *)
      echo "Unsupported argument: ${arg}" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ "${CONFIRM_PROMOTE}" != "true" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Promote this standby to primary? Type PROMOTE: " answer
    if [[ "${answer}" != "PROMOTE" ]]; then
      echo "Cancelled."
      exit 1
    fi
  else
    echo "Refusing to promote without CONFIRM_PROMOTE=true or --yes." >&2
    exit 1
  fi
fi

if [[ -z "${OLD_PRIMARY_SSH}" && "${ALLOW_UNFENCED_PROMOTE}" != "true" ]]; then
  echo "Refusing to promote without OLD_PRIMARY_SSH fencing. If the old primary is unreachable, set ALLOW_UNFENCED_PROMOTE=true or pass --allow-unfenced." >&2
  exit 1
fi

cd "${PROJECT_DIR}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
fi
if [[ ! -f "${PRIMARY_COMPOSE_FILE}" ]]; then
  echo "Prepared primary compose file not found: ${PROJECT_DIR}/${PRIMARY_COMPOSE_FILE}" >&2
  exit 1
fi

COMPOSE=(docker compose -f "${COMPOSE_FILE}")

read_recovery_state() {
  "${COMPOSE[@]}" exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT pg_is_in_recovery()"'
}

recovery_state="$(read_recovery_state)"
if [[ "${recovery_state}" != "t" ]]; then
  echo "Local Postgres is not in recovery (pg_is_in_recovery=${recovery_state}). Refusing to promote." >&2
  exit 1
fi

if [[ -n "${OLD_PRIMARY_SSH}" ]]; then
  echo "Fencing old primary app/bot on ${OLD_PRIMARY_SSH}..."
  ssh -o BatchMode=yes -o ConnectTimeout=10 "${OLD_PRIMARY_SSH}" \
    "cd '${OLD_PRIMARY_PROJECT_DIR}' && docker compose -f '${OLD_PRIMARY_COMPOSE_FILE}' stop app bot"
else
  echo "WARNING: OLD_PRIMARY_SSH is empty and ALLOW_UNFENCED_PROMOTE=true; old primary was not fenced by this script." >&2
fi

echo "Promoting local PostgreSQL..."
"${COMPOSE[@]}" exec -T db sh -lc 'pg_ctl promote -D "$PGDATA"'

for _ in $(seq 1 30); do
  recovery_state="$(read_recovery_state || true)"
  if [[ "${recovery_state}" == "f" ]]; then
    break
  fi
  sleep 1
done

if [[ "${recovery_state}" != "f" ]]; then
  echo "PostgreSQL did not leave recovery in time." >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%d%H%M%S)"
backup_file="${COMPOSE_FILE}.pre-promote.${timestamp}"
cp "${COMPOSE_FILE}" "${backup_file}"
cp "${PRIMARY_COMPOSE_FILE}" "${COMPOSE_FILE}"
echo "Swapped ${COMPOSE_FILE}; previous standby compose saved as ${backup_file}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now mvn-media-sync.timer mvn-media-sync.service >/dev/null 2>&1 || true
fi

echo "Starting promoted primary services..."
"${COMPOSE[@]}" up -d db app

echo "Verifying local readiness..."
for _ in $(seq 1 30); do
  if curl -fsS "${LOCAL_READY_URL}" >/tmp/mvn-promote-ready.out; then
    cat /tmp/mvn-promote-ready.out
    printf '\n'
    echo "Promote completed. Update GitHub variables and Cloudflare pool/fallback now."
    exit 0
  fi
  sleep 2
done

"${COMPOSE[@]}" logs --tail=120 app
echo "Promoted DB, but API readiness did not become healthy." >&2
exit 1
