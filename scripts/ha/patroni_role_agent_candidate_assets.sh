#!/usr/bin/env bash

# Shell library for transactional installation of the Patroni role-agent
# runtime. The caller supplies source/target paths, PROJECT_DIR,
# ROLE_AGENT_UNIT and atomic file helpers.

PATRONI_ROLE_ASSET_SOURCES=(
  "${ROLE_IDENTITY_SOURCE}"
  "${ROLE_AGENT_CONFIG_SOURCE}"
  "${ROLE_COMPOSE_RUNTIME_SOURCE}"
  "${ROLE_UNIT_SOURCE}"
  "${ROLE_AGENT_SOURCE}"
)
PATRONI_ROLE_ASSET_TARGETS=(
  "${ROLE_IDENTITY_TARGET}"
  "${ROLE_AGENT_CONFIG_TARGET}"
  "${ROLE_COMPOSE_RUNTIME_TARGET}"
  "${ROLE_UNIT_TARGET}"
  "${ROLE_AGENT_TARGET}"
)
PATRONI_ROLE_ASSET_MODES=(0644 0644 0644 0644 0755)
PATRONI_ROLE_ASSET_LABELS=(
  role-identity
  role-agent-config
  compose-runtime
  role-agent-unit
  role-agent
)
PATRONI_ROLE_ASSET_NAMES=(
  "identity helper"
  "role agent config"
  "compose runtime"
  "role agent unit"
  "role agent"
)
PATRONI_ROLE_ASSET_BACKUPS=("" "" "" "" "")
PATRONI_ROLE_ASSET_PREEXISTED=(false false false false false)
PATRONI_ROLE_ASSETS_CHANGED=false

patroni_role_assets_cleanup_backups() {
  local failed=false
  local index=""

  for index in "${!PATRONI_ROLE_ASSET_TARGETS[@]}"; do
    if [[ -n "${PATRONI_ROLE_ASSET_BACKUPS[${index}]}" ]]; then
      rm -f -- "${PATRONI_ROLE_ASSET_BACKUPS[${index}]}" || failed=true
      PATRONI_ROLE_ASSET_BACKUPS[index]=""
    fi
  done
  [[ "${failed}" == "false" ]]
}

patroni_role_assets_backups_present() {
  local backup=""
  for backup in "${PATRONI_ROLE_ASSET_BACKUPS[@]}"; do
    [[ -z "${backup}" ]] || return 0
  done
  return 1
}

patroni_role_assets_backup() {
  local index=""
  local target=""
  local backup=""

  for index in "${!PATRONI_ROLE_ASSET_TARGETS[@]}"; do
    target="${PATRONI_ROLE_ASSET_TARGETS[${index}]}"
    if [[ -e "${target}" || -L "${target}" ]]; then
      [[ -f "${target}" && ! -L "${target}" ]] || {
        echo "existing Patroni ${PATRONI_ROLE_ASSET_NAMES[${index}]} target is unsafe: ${target}" >&2
        return 1
      }
    fi
  done
  if { [[ -f "${ROLE_AGENT_TARGET}" ]] && [[ ! -f "${ROLE_UNIT_TARGET}" ]]; } \
    || { [[ ! -f "${ROLE_AGENT_TARGET}" ]] && [[ -f "${ROLE_UNIT_TARGET}" ]]; }; then
    echo "existing Patroni role agent executable/unit bundle is incomplete" >&2
    return 1
  fi
  if [[ -f "${ROLE_AGENT_TARGET}" ]]; then
    systemctl is-active --quiet "${ROLE_AGENT_UNIT}" || {
      echo "existing Patroni role agent unit is not active" >&2
      return 1
    }
  fi

  for index in "${!PATRONI_ROLE_ASSET_TARGETS[@]}"; do
    target="${PATRONI_ROLE_ASSET_TARGETS[${index}]}"
    [[ -f "${target}" ]] || continue
    backup="$(mktemp "${PROJECT_DIR}/.patroni-${PATRONI_ROLE_ASSET_LABELS[${index}]}.backup.XXXXXX")"
    if ! cp -p -- "${target}" "${backup}"; then
      rm -f -- "${backup}"
      patroni_role_assets_cleanup_backups || true
      return 1
    fi
    PATRONI_ROLE_ASSET_BACKUPS[index]="${backup}"
    PATRONI_ROLE_ASSET_PREEXISTED[index]=true
  done
}

patroni_role_assets_install() {
  local index=""
  local source=""

  for source in "${PATRONI_ROLE_ASSET_SOURCES[@]}"; do
    [[ -f "${source}" && ! -L "${source}" ]] || {
      echo "Patroni role agent source bundle is incomplete" >&2
      return 1
    }
  done

  PATRONI_ROLE_ASSETS_CHANGED=true
  for index in "${!PATRONI_ROLE_ASSET_TARGETS[@]}"; do
    atomic_install_file \
      "${PATRONI_ROLE_ASSET_SOURCES[${index}]}" \
      "${PATRONI_ROLE_ASSET_TARGETS[${index}]}" \
      "${PATRONI_ROLE_ASSET_MODES[${index}]}"
  done
  patroni_role_assets_cleanup_sources
  systemctl daemon-reload
  systemctl restart "${ROLE_AGENT_UNIT}"
  systemctl is-active --quiet "${ROLE_AGENT_UNIT}"
}

patroni_role_assets_cleanup_sources() {
  local source=""
  local failed=false

  for source in "${PATRONI_ROLE_ASSET_SOURCES[@]}"; do
    [[ -z "${source}" ]] || rm -f -- "${source}" || failed=true
  done
  [[ "${failed}" == "false" ]]
}

patroni_role_assets_restore() {
  [[ "${PATRONI_ROLE_ASSETS_CHANGED}" == "true" ]] || return 0
  local failed=false
  local index=""

  systemctl stop "${ROLE_AGENT_UNIT}" >/dev/null 2>&1 || failed=true

  # Restore dependencies first while the service is stopped. The executable is
  # restored last so no automatic restart can observe a partially old bundle.
  for index in 0 1 2; do
    if [[ "${PATRONI_ROLE_ASSET_PREEXISTED[${index}]}" == "true" ]]; then
      atomic_restore_file \
        "${PATRONI_ROLE_ASSET_BACKUPS[${index}]}" \
        "${PATRONI_ROLE_ASSET_TARGETS[${index}]}" || failed=true
    fi
  done
  if [[ "${PATRONI_ROLE_ASSET_PREEXISTED[3]}" == "true" ]]; then
    atomic_restore_file \
      "${PATRONI_ROLE_ASSET_BACKUPS[3]}" \
      "${PATRONI_ROLE_ASSET_TARGETS[3]}" || failed=true
  else
    rm -f -- "${PATRONI_ROLE_ASSET_TARGETS[3]}" || failed=true
  fi
  if [[ "${PATRONI_ROLE_ASSET_PREEXISTED[4]}" == "true" ]]; then
    atomic_restore_file \
      "${PATRONI_ROLE_ASSET_BACKUPS[4]}" \
      "${PATRONI_ROLE_ASSET_TARGETS[4]}" || failed=true
  else
    rm -f -- "${PATRONI_ROLE_ASSET_TARGETS[4]}" || failed=true
  fi

  # New-only dependency modules are removed only after the prior executable is
  # back in place (or the new-only executable has been removed).
  for index in 0 1 2; do
    if [[ "${PATRONI_ROLE_ASSET_PREEXISTED[${index}]}" != "true" ]]; then
      rm -f -- "${PATRONI_ROLE_ASSET_TARGETS[${index}]}" || failed=true
    fi
  done
  systemctl daemon-reload || failed=true

  if [[ "${PATRONI_ROLE_ASSET_PREEXISTED[4]}" == "true" ]]; then
    systemctl restart "${ROLE_AGENT_UNIT}" || failed=true
    systemctl is-active --quiet "${ROLE_AGENT_UNIT}" || failed=true
  else
    if systemctl is-active --quiet "${ROLE_AGENT_UNIT}"; then
      echo "new Patroni role agent unit remained active after stop" >&2
      failed=true
    fi
  fi
  [[ "${failed}" == "false" ]]
}
