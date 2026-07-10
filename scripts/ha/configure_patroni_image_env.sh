#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${PATRONI_ENV_FILE:?set PATRONI_ENV_FILE}"

IFS= read -r patroni_image
[[ "${patroni_image}" =~ ^ghcr\.io/mvnby/air-api/patroni@sha256:[0-9a-f]{64}$ ]] || {
  echo "PATRONI_IMAGE must be the immutable MVN Patroni GHCR digest" >&2
  exit 1
}
[[ -f "${ENV_FILE}" ]] || {
  echo "env file is missing: ${ENV_FILE}" >&2
  exit 1
}

backup="${ENV_FILE}.bak-patroni-image-$(date -u +%Y%m%dT%H%M%SZ)"
cp -a "${ENV_FILE}" "${backup}"
temporary="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
trap 'rm -f "${temporary}"' EXIT
grep -v '^PATRONI_IMAGE=' "${ENV_FILE}" > "${temporary}" || true
printf 'PATRONI_IMAGE=%s\n' "${patroni_image}" >> "${temporary}"
if ! chmod --reference="${ENV_FILE}" "${temporary}" 2>/dev/null; then
  mode="$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || stat -f '%Lp' "${ENV_FILE}")"
  chmod "${mode}" "${temporary}"
fi
chown --reference="${ENV_FILE}" "${temporary}" 2>/dev/null || true
mv "${temporary}" "${ENV_FILE}"
trap - EXIT

echo "patroni_image_env=prepared backup=${backup}"
