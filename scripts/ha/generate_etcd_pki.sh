#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${ETCD_PKI_OUTPUT_DIR:-}"
FORCE="${ETCD_PKI_FORCE:-false}"
VALID_DAYS="${ETCD_PKI_VALID_DAYS:-825}"

usage() {
  cat <<'USAGE'
Usage:
  ETCD_PKI_OUTPUT_DIR=/secure/path bash scripts/ha/generate_etcd_pki.sh

Generates one private CA, three node certificates, and an operator certificate.
The CA private key stays under ca-private/ and must never be copied to a server.
Set ETCD_PKI_FORCE=true only to replace an uninstalled test PKI.
USAGE
}

log() {
  printf '[etcd-pki][%s] %s\n' "$1" "$2"
}

[[ "${1:-}" != "--help" && "${1:-}" != "-h" ]] || {
  usage
  exit 0
}
[[ -n "${OUTPUT_DIR}" ]] || {
  log error "ETCD_PKI_OUTPUT_DIR is required"
  exit 1
}
[[ "${VALID_DAYS}" =~ ^[1-9][0-9]*$ ]] || {
  log error "ETCD_PKI_VALID_DAYS must be a positive integer"
  exit 1
}
command -v openssl >/dev/null 2>&1 || {
  log error "openssl is required"
  exit 1
}

if [[ -e "${OUTPUT_DIR}" ]]; then
  if [[ "${FORCE}" != "true" ]]; then
    log error "output already exists; refusing to replace ${OUTPUT_DIR}"
    exit 1
  fi
  [[ "${OUTPUT_DIR}" == /* && "${OUTPUT_DIR}" != "/" ]] || {
    log error "refusing unsafe output path"
    exit 1
  }
  rm -rf "${OUTPUT_DIR}"
fi

umask 077
mkdir -p "${OUTPUT_DIR}/ca-private" "${OUTPUT_DIR}/nodes" "${OUTPUT_DIR}/operator"
ca_key="${OUTPUT_DIR}/ca-private/ca.key"
ca_cert="${OUTPUT_DIR}/ca.crt"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out "${ca_key}" >/dev/null 2>&1
openssl req -x509 -new -sha256 \
  -key "${ca_key}" \
  -out "${ca_cert}" \
  -days "${VALID_DAYS}" \
  -subj "/CN=MVN PostgreSQL HA etcd CA" >/dev/null 2>&1

issue_certificate() {
  local name="$1"
  local output="$2"
  local usage="$3"
  local sans="${4:-}"
  local config="${OUTPUT_DIR}/.${name}.cnf"
  local csr="${OUTPUT_DIR}/.${name}.csr"

  mkdir -p "${output}"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "${output}/node.key" >/dev/null 2>&1
  {
    echo '[req]'
    echo 'distinguished_name = dn'
    echo 'prompt = no'
    echo 'req_extensions = req_ext'
    echo '[dn]'
    echo "CN = ${name}"
    echo '[req_ext]'
    echo "extendedKeyUsage = ${usage}"
    if [[ -n "${sans}" ]]; then
      echo "subjectAltName = ${sans}"
    fi
  } > "${config}"
  openssl req -new -sha256 -key "${output}/node.key" -out "${csr}" -config "${config}" >/dev/null 2>&1
  openssl x509 -req -sha256 \
    -in "${csr}" \
    -CA "${ca_cert}" \
    -CAkey "${ca_key}" \
    -CAcreateserial \
    -out "${output}/node.crt" \
    -days "${VALID_DAYS}" \
    -copy_extensions copy >/dev/null 2>&1
  cp "${ca_cert}" "${output}/ca.crt"
  chmod 0600 "${output}/node.key"
  chmod 0644 "${output}/node.crt" "${output}/ca.crt"
  rm -f "${config}" "${csr}"
  openssl verify -CAfile "${ca_cert}" "${output}/node.crt" >/dev/null
}

issue_certificate \
  mvn-api \
  "${OUTPUT_DIR}/nodes/mvn-api" \
  serverAuth,clientAuth \
  'IP:10.77.0.2,IP:127.0.0.1,DNS:mvn-api,DNS:api.mvn.by'
issue_certificate \
  zakup \
  "${OUTPUT_DIR}/nodes/zakup" \
  serverAuth,clientAuth \
  'IP:10.77.0.1,IP:127.0.0.1,DNS:zakup,DNS:maxikor.fun'
issue_certificate \
  mvn-web \
  "${OUTPUT_DIR}/nodes/mvn-web" \
  serverAuth,clientAuth \
  'IP:10.77.0.3,IP:127.0.0.1,DNS:mvn-web,DNS:www.mvn.by'
issue_certificate operator "${OUTPUT_DIR}/operator" clientAuth

mv "${OUTPUT_DIR}/operator/node.key" "${OUTPUT_DIR}/operator/operator.key"
mv "${OUTPUT_DIR}/operator/node.crt" "${OUTPUT_DIR}/operator/operator.crt"
rm -f "${OUTPUT_DIR}/operator/ca.crt" "${OUTPUT_DIR}/ca.srl"

log "done" "generated CA, 3 node certificates, and operator certificate under ${OUTPUT_DIR}"
