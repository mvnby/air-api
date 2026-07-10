#!/usr/bin/env sh
set -eu

PGDATA="${PATRONI_POSTGRESQL_DATA_DIR:-${PGDATA:-/var/lib/postgresql/data}}"
CONFIG_FILE="${PATRONI_CONFIG_FILE:-/etc/patroni/patroni.yml}"
ALLOW_BOOTSTRAP="${PATRONI_ALLOW_BOOTSTRAP:-false}"

prepare_etcd_tls() {
  runtime_dir=/run/patroni-etcd-pki
  ca_source="${PATRONI_ETCD3_CACERT:-}"
  cert_source="${PATRONI_ETCD3_CERT:-}"
  key_source="${PATRONI_ETCD3_KEY:-}"

  for source in "${ca_source}" "${cert_source}" "${key_source}"; do
    if [ ! -f "${source}" ]; then
      echo "[patroni-entrypoint][error] etcd TLS file is missing: ${source:-<empty>}" >&2
      exit 1
    fi
  done

  mkdir -p "${runtime_dir}"
  chmod 0700 "${runtime_dir}"
  chown postgres:postgres "${runtime_dir}"
  cp "${ca_source}" "${runtime_dir}/ca.crt"
  cp "${cert_source}" "${runtime_dir}/node.crt"
  cp "${key_source}" "${runtime_dir}/node.key"
  chown postgres:postgres \
    "${runtime_dir}/ca.crt" "${runtime_dir}/node.crt" "${runtime_dir}/node.key"
  chmod 0400 \
    "${runtime_dir}/ca.crt" "${runtime_dir}/node.crt" "${runtime_dir}/node.key"
  export PATRONI_ETCD3_CACERT="${runtime_dir}/ca.crt"
  export PATRONI_ETCD3_CERT="${runtime_dir}/node.crt"
  export PATRONI_ETCD3_KEY="${runtime_dir}/node.key"
}

if [ "$(id -u)" = "0" ]; then
  mkdir -p "${PGDATA}" "$(dirname "${CONFIG_FILE}")" /var/run/postgresql
  chown postgres:postgres "${PGDATA}" "$(dirname "${CONFIG_FILE}")" /var/run/postgresql
  chmod 0700 "${PGDATA}"
  if [ "${PATRONI_ETCD3_PROTOCOL:-https}" = "https" ]; then
    prepare_etcd_tls
  fi
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
