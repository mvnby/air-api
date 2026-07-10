#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${PATRONI_ENV_FILE:?set PATRONI_ENV_FILE}"
REPLICATION_USERNAME="${PATRONI_REPLICATION_USERNAME:-mvn_replicator}"

IFS= read -r replication_password
[[ "${#replication_password}" -ge 16 ]] || {
  echo "replication password must contain at least 16 characters" >&2
  exit 1
}
[[ -f "${ENV_FILE}" ]] || {
  echo "env file is missing: ${ENV_FILE}" >&2
  exit 1
}

backup="${ENV_FILE}.bak-patroni-$(date -u +%Y%m%dT%H%M%SZ)"
cp -a "${ENV_FILE}" "${backup}"
temporary="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
trap 'rm -f "${temporary}"' EXIT
grep -vE '^PATRONI_REPLICATION_(USERNAME|PASSWORD)=' "${ENV_FILE}" > "${temporary}" || true
printf 'PATRONI_REPLICATION_USERNAME=%s\n' "${REPLICATION_USERNAME}" >> "${temporary}"
printf 'PATRONI_REPLICATION_PASSWORD=%s\n' "${replication_password}" >> "${temporary}"
if ! chmod --reference="${ENV_FILE}" "${temporary}" 2>/dev/null; then
  mode="$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || stat -f '%Lp' "${ENV_FILE}")"
  chmod "${mode}" "${temporary}"
fi
chown --reference="${ENV_FILE}" "${temporary}" 2>/dev/null || true
mv "${temporary}" "${ENV_FILE}"
trap - EXIT

echo "patroni_replication_env=prepared backup=${backup}"
