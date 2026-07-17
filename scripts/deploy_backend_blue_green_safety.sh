#!/usr/bin/env bash
# shellcheck disable=SC2154

# Runtime-truth and rollback safety helpers sourced by deploy_backend_blue_green.sh.

rollback_buffer_slot=""
rollback_buffer_service=""
rollback_buffer_port=""
rollback_buffer_override=""
rollback_buffer_started=false
rollback_buffer_routed=false
ROLLBACK_BUFFER_COMPOSE=()

require_pitr_maintenance_clear_or_attested_scrub() {
  local transaction_id="${API_PITR_MAINTENANCE_TRANSACTION_ID:-}"
  local pinned_root="/usr/local/libexec/mvn-pitr"

  if [[ ! -e "${PITR_MAINTENANCE_MARKER}" && ! -L "${PITR_MAINTENANCE_MARKER}" ]]; then
    if [[ -n "${transaction_id}" ]]; then
      log error "PITR scrub attestation was supplied without active maintenance"
      return 1
    fi
    return 0
  fi
  if [[ -z "${transaction_id}" ]]; then
    log error "PITR release maintenance is active: ${PITR_MAINTENANCE_MARKER}"
    return 1
  fi
  [[ "${transaction_id}" =~ ^[0-9a-f]{32}$ ]] || {
    log error "PITR scrub transaction id is invalid"
    return 1
  }
  [[ "$0" == "${pinned_root}/deploy_backend_blue_green.sh" \
    && "${DEPLOY_LOCK_FD}" == "9" \
    && "${DEPLOY_LOCK_HELPER}" == "${pinned_root}/safe_deploy_lock.py" \
    && "${SAFETY_HELPER}" == "${pinned_root}/deploy_backend_blue_green_safety.sh" \
    && "${CAPACITY_HELPER}" == "${pinned_root}/require_deploy_capacity.sh" \
    && "${PITR_MARKER_VALIDATOR}" == "${pinned_root}/verify_pitr_maintenance_marker.py" ]] || {
    log error "PITR scrub helper attestation is not pinned"
    return 1
  }
  [[ -f "${PITR_MARKER_VALIDATOR}" && ! -L "${PITR_MARKER_VALIDATOR}" ]] || {
    log error "PITR maintenance marker validator is missing or unsafe"
    return 1
  }
  python3 "${PITR_MARKER_VALIDATOR}" marker "${transaction_id}" || {
    log error "PITR maintenance marker attestation failed"
    return 1
  }
  log pitr "attested internal PITR runtime scrub for transaction ${transaction_id}"
}

wait_service_running() {
  local service="$1"
  local running

  for _ in $(seq 1 15); do
    running="$("${COMPOSE[@]}" ps --status running --services 2>/dev/null || true)"
    if grep -Fxq "${service}" <<<"${running}"; then
      return 0
    fi
    sleep 1
  done
  log error "compose service is not running: ${service}"
  return 1
}

inspect_service_runtime_image() {
  local service="$1"
  local container_ids
  local container_id
  local image

  container_ids="$("${COMPOSE[@]}" ps -q "${service}")" || {
    log error "could not resolve the running container for ${service}"
    return 1
  }
  if [[ -z "${container_ids}" || "${container_ids}" == *$'\n'* ]]; then
    log error "expected exactly one running container for ${service}"
    return 1
  fi
  container_id="${container_ids}"
  image="$(docker inspect --format '{{.Config.Image}}' "${container_id}")" || {
    log error "could not inspect the runtime image for ${service}"
    return 1
  }
  if [[ -z "${image}" || "${image}" == *$'\n'* ]] \
    || ! is_immutable_image "${image}"; then
    log error "runtime image for ${service} is missing, ambiguous, or mutable"
    return 1
  fi
  printf '%s\n' "${image}"
}

service_runtime_matches_image() {
  local service="$1"
  local expected_image="$2"
  local runtime_image

  runtime_image="$(inspect_service_runtime_image "${service}" 2>/dev/null)" \
    || return 1
  [[ "${runtime_image}" == "${expected_image}" ]]
}

monotonic_now_ns() {
  python3 - <<'PY'
import time

print(time.monotonic_ns())
PY
}

scheduler_stability_elapsed() {
  local started_ns="$1"
  local current_ns="$2"

  python3 - "${started_ns}" "${current_ns}" "${SCHEDULER_STABILITY_SECONDS}" <<'PY'
import decimal
import sys

started_ns = int(sys.argv[1])
current_ns = int(sys.argv[2])
required_ns = decimal.Decimal(sys.argv[3]) * decimal.Decimal(1_000_000_000)
if decimal.Decimal(current_ns - started_ns) < required_ns:
    raise SystemExit(1)
PY
}

rollback_record_slot() {
  local slot="$1"
  if [[ "${slot}" == "legacy" ]]; then
    rm -f "${ACTIVE_SLOT_FILE}"
  else
    atomic_write_line "${ACTIVE_SLOT_FILE}" "${slot}" 600
  fi
}

rollback_select_buffer_slot() {
  local slot
  for slot in legacy blue green; do
    if [[ "${slot}" != "${active_slot}" && "${slot}" != "${candidate_slot}" ]]; then
      printf '%s\n' "${slot}"
      return 0
    fi
  done
  return 1
}

rollback_write_buffer_override() {
  local quoted_image
  rollback_buffer_override="${TMP_DIR}/rollback-api-buffer.compose.yml"
  if ! quoted_image="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "${previous_image}")"; then
    log error "could not encode the rollback buffer image"
    return 1
  fi
  if ! cat > "${rollback_buffer_override}" <<EOF
services:
  ${rollback_buffer_service}:
    image: ${quoted_image}
    restart: unless-stopped
    environment:
      APP_ROLE: primary
      API_READY_ENABLED: "true"
      DB_BOOTSTRAP_ENABLED: "false"
      SCHEDULER_ENABLED: "false"
      BOT_ENABLED: "false"
      MAIL_IMAP_AUTO_IMPORT_ENABLED: "false"
      MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED: "false"
      CLOUDFLARE_PURGE_ENABLED: "false"
      CLOUDFLARE_PURGE_DRY_RUN: "true"
EOF
  then
    log error "could not write the rollback buffer Compose override"
    return 1
  fi
  if ! chmod 600 "${rollback_buffer_override}"; then
    log error "could not secure the rollback buffer Compose override"
    return 1
  fi
  ROLLBACK_BUFFER_COMPOSE=(
    docker compose -f "${COMPOSE_FILE}" -f "${rollback_buffer_override}" --profile bluegreen
  )
}

rollback_buffer_stop() {
  if [[ "${rollback_buffer_started}" != "true" ]]; then
    return 0
  fi
  if ! "${ROLLBACK_BUFFER_COMPOSE[@]}" rm -s -f "${rollback_buffer_service}" \
    >/dev/null 2>&1; then
    log error "rollback buffer cleanup failed for ${rollback_buffer_service}"
    return 1
  fi
  rollback_buffer_started=false
  rm -f "${PROJECT_DIR}/.rollback-api-buffer.compose.yml"
}

rollback_buffer_start() {
  rollback_buffer_slot="$(rollback_select_buffer_slot)" || {
    log error "cannot select a third API slot for rollback buffer"
    return 1
  }
  rollback_buffer_service="$(service_for_slot "${rollback_buffer_slot}")"
  rollback_buffer_port="$(port_for_slot "${rollback_buffer_slot}")"
  rollback_write_buffer_override || return 1

  log rollback "starting API-only rollback buffer ${rollback_buffer_slot} on ${rollback_buffer_port}"
  rollback_buffer_started=true
  if ! "${ROLLBACK_BUFFER_COMPOSE[@]}" up -d --no-deps --force-recreate \
    "${rollback_buffer_service}"; then
    log error "rollback buffer container failed to start"
    return 1
  fi
  if ! wait_ready_url \
    "rollback_buffer" \
    "http://127.0.0.1:${rollback_buffer_port}/api/ready"; then
    log error "rollback buffer API did not become ready"
    if ! rollback_buffer_stop; then
      rollback_preserve_buffer_state
    fi
    return 1
  fi
}

rollback_route_slot() {
  local target_slot="$1"
  local fallback_slot="$2"

  if write_upstream "${target_slot}" && reload_proxy && rollback_record_slot "${target_slot}"; then
    if [[ "${target_slot}" == "${rollback_buffer_slot}" ]]; then
      rollback_buffer_routed=true
    else
      rollback_buffer_routed=false
    fi
    return 0
  fi

  log error "failed to route ${target_slot}; restoring ${fallback_slot}"
  write_upstream "${fallback_slot}" || true
  reload_proxy || true
  rollback_record_slot "${fallback_slot}" || true
  if [[ "${fallback_slot}" == "${rollback_buffer_slot}" ]]; then
    rollback_buffer_routed=true
  else
    rollback_buffer_routed=false
  fi
  return 1
}

rollback_preserve_buffer_state() {
  local image_state_synced=true

  if [[ "${rollback_buffer_routed}" == "true" ]]; then
    if rollback_restore_previous_image_state; then
      summary "rollback_buffer_image_state_synced=true"
    else
      image_state_synced=false
      summary "rollback_buffer_image_state_synced=false"
      log error "rollback buffer is routed, but the previous image state could not be fully synchronized"
    fi
  fi
  if ! cp -f "${rollback_buffer_override}" "${PROJECT_DIR}/.rollback-api-buffer.compose.yml" \
    || ! chmod 600 "${PROJECT_DIR}/.rollback-api-buffer.compose.yml"; then
    log error "could not preserve the rollback buffer Compose override"
    return 1
  fi
  summary "rollback_buffer_container_present=true"
  summary "rollback_buffer_routed=${rollback_buffer_routed}"
  summary "rollback_buffer_slot=${rollback_buffer_slot}"
  summary "rollback_buffer_service=${rollback_buffer_service}"
  summary "rollback_buffer_image=${previous_image}"
  summary "rollback_buffer_override=${PROJECT_DIR}/.rollback-api-buffer.compose.yml"
  summary "rollback_buffer_cleanup=docker compose -f ${COMPOSE_FILE} -f ${PROJECT_DIR}/.rollback-api-buffer.compose.yml --profile bluegreen rm -s -f ${rollback_buffer_service}"
  [[ "${image_state_synced}" == "true" ]]
}

rollback_stop_service() {
  local service="$1"
  "${COMPOSE[@]}" stop -t "${SERVICE_STOP_TIMEOUT_SECONDS}" "${service}" \
    && "${COMPOSE[@]}" rm -f "${service}"
}

rollback_restore_previous_image_state() {
  is_immutable_image "${previous_image}" || {
    log error "cannot restore a non-immutable previous image"
    return 1
  }

  export BACKEND_IMAGE="${previous_image}"
  if [[ "${env_updated}" == "true" ]]; then
    if ! write_backend_image "${previous_image}"; then
      log error "could not restore BACKEND_IMAGE in ${ENV_FILE}"
      return 1
    fi
  fi
}

rollback_restore_candidate_from_buffer() {
  local candidate_ready=false

  export BACKEND_IMAGE="${REQUESTED_IMAGE}"
  if [[ "${env_updated}" == "true" ]]; then
    if ! write_backend_image "${REQUESTED_IMAGE}"; then
      log error "could not synchronize BACKEND_IMAGE before candidate recovery"
      rollback_preserve_buffer_state
      summary "candidate_image_state_synced=false"
      summary "candidate_api_fallback_ready=false"
      return 1
    fi
  fi
  summary "candidate_image_state_synced=true"
  candidate_started=true
  if "${COMPOSE[@]}" up -d --no-deps --force-recreate "${candidate_service}" \
    && wait_ready_url \
      "rollback_candidate_fallback" \
      "http://127.0.0.1:${candidate_port}/api/ready" \
    && wait_scheduler_running_url \
      "rollback_candidate_scheduler" \
      "http://127.0.0.1:${candidate_port}/api/ready"; then
    candidate_ready=true
  fi

  if [[ "${candidate_ready}" == "true" ]] \
    && rollback_route_slot "${candidate_slot}" "${rollback_buffer_slot}"; then
    if ! rollback_buffer_stop; then
      rollback_preserve_buffer_state
      summary "rollback_buffer_cleanup=false"
      return 1
    fi
    summary "candidate_api_fallback_ready=true"
    return 0
  fi

  rollback_preserve_buffer_state
  summary "candidate_api_fallback_ready=false"
  return 1
}

rollback_without_buffer() {
  local image_state_synced=true

  if [[ "${nginx_switch_attempted}" == "true" && -f "${NGINX_UPSTREAM_FILE}" ]]; then
    if ! rollback_route_slot "${active_slot}" "${candidate_slot}"; then
      summary "old_route_confirmed=false"
      summary "candidate_preserved=true"
      return 1
    fi
  fi
  summary "old_route_confirmed=true"

  if ! rollback_restore_previous_image_state; then
    image_state_synced=false
  fi
  if [[ "${candidate_started}" == "true" && -n "${candidate_service}" ]]; then
    if ! rollback_stop_service "${candidate_service}"; then
      summary "candidate_stop_confirmed=false"
      return 1
    fi
    candidate_started=false
  fi
  summary "candidate_stop_confirmed=true"
  if ! rollback_record_slot "${active_slot}"; then
    summary "old_slot_recorded=false"
    return 1
  fi
  if [[ "${image_state_synced}" != "true" ]]; then
    summary "previous_image_state_synced=false"
    return 1
  fi
  summary "previous_image_state_synced=true"
}

rollback_on_error() {
  local exit_code=$?
  local old_ready=false
  trap - ERR
  set +e
  log rollback "activation failed; restoring ${active_slot} on port ${active_port}"

  if [[ "${old_service_stop_started}" != "true" ]]; then
    if rollback_without_buffer; then
      summary "status=rolled_back"
    else
      summary "status=rollback_failed"
    fi
    summary "failed_candidate=${REQUESTED_IMAGE}"
    if [[ "$(parse_upstream_slot 2>/dev/null || true)" == "${active_slot}" ]]; then
      summary "restored_slot=${active_slot}"
      summary "restored_port=${active_port}"
    fi
    exit "${exit_code}"
  fi

  if ! rollback_buffer_start \
    || ! rollback_route_slot "${rollback_buffer_slot}" "${candidate_slot}"; then
    if ! rollback_buffer_stop; then
      rollback_preserve_buffer_state
    fi
    summary "status=rollback_failed"
    summary "failed_candidate=${REQUESTED_IMAGE}"
    summary "candidate_preserved=true"
    exit "${exit_code}"
  fi

  if ! rollback_stop_service "${candidate_service}"; then
    log error "candidate did not stop cleanly; refusing to start another scheduler owner"
    rollback_preserve_buffer_state
    summary "status=rollback_buffer_active"
    summary "candidate_stop_confirmed=false"
    exit "${exit_code}"
  fi
  candidate_started=false

  export BACKEND_IMAGE="${previous_image}"
  if "${COMPOSE[@]}" up -d --no-deps "${active_service}" \
    && wait_ready_url "rollback_old" "http://127.0.0.1:${active_port}/api/ready"; then
    old_ready=true
  fi

  if [[ "${old_ready}" == "true" ]] \
    && rollback_route_slot "${active_slot}" "${rollback_buffer_slot}"; then
    local previous_image_state_synced=true
    if rollback_restore_previous_image_state; then
      summary "previous_image_state_synced=true"
    else
      previous_image_state_synced=false
      summary "previous_image_state_synced=false"
    fi
    if ! rollback_buffer_stop; then
      rollback_preserve_buffer_state
      summary "rollback_buffer_cleanup=false"
    fi
    if [[ "${previous_image_state_synced}" == "true" ]]; then
      summary "status=rolled_back"
    else
      summary "status=rollback_failed"
    fi
    summary "failed_candidate=${REQUESTED_IMAGE}"
    summary "restored_slot=${active_slot}"
    summary "restored_port=${active_port}"
    exit "${exit_code}"
  fi

  log error "rollback old slot is not ready; candidate recovery will run behind the API buffer"
  if ! rollback_stop_service "${active_service}"; then
    log error "unhealthy old slot could not be removed; refusing candidate recovery"
    rollback_preserve_buffer_state
    summary "status=rollback_buffer_active"
    summary "old_slot_stop_confirmed=false"
    exit "${exit_code}"
  fi
  if rollback_restore_candidate_from_buffer; then
    summary "status=rollback_failed"
    summary "failed_candidate=${REQUESTED_IMAGE}"
    summary "old_slot_ready=false"
  else
    summary "status=rollback_buffer_active"
    summary "failed_candidate=${REQUESTED_IMAGE}"
    summary "old_slot_ready=false"
  fi
  exit "${exit_code}"
}
