#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-prepare}"
PROJECT_DIR="${GOOGLE_OAUTH_PROJECT_DIR:-${API_PROJECT_DIR:-/opt/air-api}}"
TOKEN_DIR="${GOOGLE_OAUTH_HOST_DIR:-${PROJECT_DIR}/google-oauth}"
TOKEN_FILE="${GOOGLE_OAUTH_HOST_TOKEN_FILE:-${TOKEN_DIR}/token.json}"
TOKEN_REQUIRED="${GOOGLE_OAUTH_TOKEN_REQUIRED:-true}"
LEGACY_TOKEN_FILE="${GOOGLE_OAUTH_LEGACY_TOKEN_FILE:-}"

log() {
  printf '[google-oauth-token][%s] %s\n' "$1" "$2"
}

fail() {
  log error "$1" >&2
  exit 1
}

validate_token() {
  python3 - "$1" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid Google OAuth token JSON: {type(exc).__name__}") from None

required = ("refresh_token", "client_id", "client_secret", "token_uri")
missing = [key for key in required if not isinstance(payload, dict) or not payload.get(key)]
if missing:
    raise SystemExit(f"Google OAuth token JSON is missing required fields: {','.join(missing)}")
PY
}

fsync_path() {
  python3 - "$1" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDONLY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
}

secure_retained_legacy_token() {
  local candidate="$1"
  [[ -e "${candidate}" || -L "${candidate}" ]] || return 0
  [[ ! -L "${candidate}" && -f "${candidate}" && -r "${candidate}" ]] || {
    fail "retained legacy token is missing or unsafe: ${candidate}"
  }
  validate_token "${candidate}"
  chmod 0600 "${candidate}"
  log permissions "retained legacy token secured at ${candidate}"
}

verify_layout() {
  python3 - "${TOKEN_DIR}" "${TOKEN_FILE}" <<'PY'
import pathlib
import stat
import sys

directory = pathlib.Path(sys.argv[1])
token = pathlib.Path(sys.argv[2])
if directory.is_symlink() or not directory.is_dir():
    raise SystemExit("Google OAuth token directory is missing or is a symlink")
if token.is_symlink() or not token.is_file():
    raise SystemExit("Google OAuth token file is missing or is a symlink")
if stat.S_IMODE(directory.stat().st_mode) != 0o700:
    raise SystemExit("Google OAuth token directory mode must be 0700")
if stat.S_IMODE(token.stat().st_mode) != 0o600:
    raise SystemExit("Google OAuth token file mode must be 0600")
PY
  validate_token "${TOKEN_FILE}"
  log verify "secure writable-directory layout is ready at ${TOKEN_FILE}"
}

[[ "${MODE}" == "prepare" || "${MODE}" == "verify" ]] || {
  echo "usage: prepare_google_oauth_token_dir.sh [prepare|verify]" >&2
  exit 2
}
[[ "${TOKEN_REQUIRED}" == "true" || "${TOKEN_REQUIRED}" == "false" ]] || {
  fail "GOOGLE_OAUTH_TOKEN_REQUIRED must be true or false"
}
[[ "$(dirname "${TOKEN_FILE}")" == "${TOKEN_DIR}" ]] || {
  fail "GOOGLE_OAUTH_HOST_TOKEN_FILE must be inside GOOGLE_OAUTH_HOST_DIR"
}
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

if [[ "${MODE}" == "verify" ]]; then
  verify_layout
  exit 0
fi

[[ -d "${PROJECT_DIR}" ]] || fail "project directory is missing: ${PROJECT_DIR}"
[[ ! -L "${TOKEN_DIR}" ]] || fail "refusing symlink token directory: ${TOKEN_DIR}"
[[ ! -e "${TOKEN_DIR}" || -d "${TOKEN_DIR}" ]] || {
  fail "token directory path is not a directory: ${TOKEN_DIR}"
}

umask 077
install -d -m 0700 "${TOKEN_DIR}"

if [[ ! -e "${TOKEN_FILE}" ]]; then
  source_token=""
  consider_legacy_token() {
    local candidate="$1"
    [[ -e "${candidate}" || -L "${candidate}" ]] || return 0
    [[ ! -L "${candidate}" ]] || fail "refusing symlink legacy token: ${candidate}"
    [[ -f "${candidate}" && -r "${candidate}" ]] || return 0
    if [[ -z "${source_token}" ]]; then
      source_token="${candidate}"
      return 0
    fi
    cmp -s "${source_token}" "${candidate}" || {
      fail "multiple different legacy tokens found; set GOOGLE_OAUTH_LEGACY_TOKEN_FILE"
    }
  }

  if [[ -n "${LEGACY_TOKEN_FILE}" ]]; then
    consider_legacy_token "${LEGACY_TOKEN_FILE}"
  else
    consider_legacy_token "${PROJECT_DIR}/token.json"
    consider_legacy_token "${PROJECT_DIR}/secrets/token.json"
  fi

  if [[ -z "${source_token}" ]]; then
    if [[ "${TOKEN_REQUIRED}" == "false" ]]; then
      chmod 0700 "${TOKEN_DIR}"
      log prepare "token is optional and no legacy file was found; directory is ready"
      exit 0
    fi
    fail "no readable legacy Google OAuth token found; refusing an auth-broken deploy"
  fi

  validate_token "${source_token}"

  temporary="$(mktemp "${TOKEN_DIR}/.token.json.migrate.XXXXXX")"
  trap 'rm -f "${temporary:-}"' EXIT
  install -m 0600 "${source_token}" "${temporary}"
  chown --reference="${source_token}" "${temporary}" 2>/dev/null || true
  fsync_path "${temporary}"
  mv -f "${temporary}" "${TOKEN_FILE}"
  fsync_path "${TOKEN_DIR}"
  trap - EXIT
  log prepare "copied the legacy token atomically; the legacy file was retained"
fi

[[ ! -L "${TOKEN_FILE}" && -f "${TOKEN_FILE}" ]] || {
  fail "refusing non-regular token file: ${TOKEN_FILE}"
}
chmod 0700 "${TOKEN_DIR}"
chmod 0600 "${TOKEN_FILE}"
verify_layout
if [[ -n "${LEGACY_TOKEN_FILE}" ]]; then
  secure_retained_legacy_token "${LEGACY_TOKEN_FILE}"
else
  secure_retained_legacy_token "${PROJECT_DIR}/token.json"
  secure_retained_legacy_token "${PROJECT_DIR}/secrets/token.json"
fi
