#!/usr/bin/env sh
set -eu

PGDATA="${PATRONI_POSTGRESQL_DATA_DIR:-${PGDATA:-/var/lib/postgresql/data}}"
CONFIG_FILE="${PATRONI_CONFIG_FILE:-/etc/patroni/patroni.yml}"
ALLOW_BOOTSTRAP="${PATRONI_ALLOW_BOOTSTRAP:-false}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p "${PGDATA}" "$(dirname "${CONFIG_FILE}")" /var/run/postgresql
  chown -R postgres:postgres "${PGDATA}" "$(dirname "${CONFIG_FILE}")" /var/run/postgresql
fi

if [ ! -s "${PGDATA}/PG_VERSION" ] && [ "${ALLOW_BOOTSTRAP}" != "true" ]; then
  echo "[patroni-entrypoint][error] PGDATA is empty and PATRONI_ALLOW_BOOTSTRAP is not true" >&2
  exit 1
fi

render-patroni-config "${CONFIG_FILE}"
chmod 0600 "${CONFIG_FILE}"
if [ "$(id -u)" = "0" ]; then
  chown postgres:postgres "${CONFIG_FILE}"
  exec su-exec postgres "$@"
fi
exec "$@"
