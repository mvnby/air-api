#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
PITR_OPERATION_ID="${PITR_OPERATION_ID:-}"
DRILL_ROOT="${DRILL_ROOT:-}"
CLEANUP_SCRIPT="${RESTORE_DRILL_CLEANUP_SCRIPT:-}"
EXPECTED_DATABASE_ROLE="${EXPECTED_DATABASE_ROLE:-}"

APP_SERVICE="app"
DB_SERVICE="db"
POSTGRES_IMAGE="postgres:15.18-alpine@sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f"
EXPECTED_DRILL_ROOT="/var/lib/mvn-postgres-pitr/logical-restore-drills"
EXPECTED_CLEANUP_SCRIPT="/usr/local/sbin/mvn-restore-drill-latest-db-cleanup"
RUNTIME_CHECK_HELPER="/usr/local/sbin/mvn-postgres-pitr-runtime-check"
RESOURCE_SIZING_HELPER="/usr/local/sbin/mvn-logical-restore-resource-sizer"
MIN_PUBLIC_TABLES="64"
MAX_RESTORED_SQL_BYTES="8589934592"
RESTORE_TIMEOUT_SECONDS="900"
POSTGRES_CONTAINER_UID="70"
POSTGRES_CONTAINER_GID="70"

umask 077
export DOCKER_CONTEXT="default"

log() {
  printf '[restore-drill] %s\n' "$*"
}

fail() {
  printf '[restore-drill][fail] %s\n' "$*" >&2
  exit 1
}

require_root_directory() {
  local path="$1"
  local metadata=""
  metadata="$(stat -Lc '%u:%g:%a:%h' "${path}" 2>/dev/null || true)"
  [[ ! -L "${path}" && -d "${path}" && "${metadata}" =~ ^0:0:700:[2-9][0-9]*$ ]] ||
    fail "logical restore-drill state directory is unsafe: ${path}"
}

ensure_postgres_image() {
  if docker image inspect "${POSTGRES_IMAGE}" >/dev/null 2>&1; then
    log "restore_image_status=cached image=${POSTGRES_IMAGE}"
    return
  fi

  log "restore_image_status=pulling image=${POSTGRES_IMAGE}"
  docker pull "${POSTGRES_IMAGE}" >/dev/null ||
    fail "could not pull the pinned PostgreSQL restore image"
  docker image inspect "${POSTGRES_IMAGE}" >/dev/null 2>&1 ||
    fail "pinned PostgreSQL restore image is unavailable after pull"
  log "restore_image_status=pulled image=${POSTGRES_IMAGE}"
}

(( EUID == 0 )) || fail "logical restore drill requires root"
[[ "${PITR_OPERATION_ID}" =~ ^[0-9a-f]{32}$ ]] ||
  fail "PITR_OPERATION_ID must be a guarded 32-character lowercase hex ID"
case "${PROJECT_DIR}:${COMPOSE_FILE}" in
  /opt/air-api:docker-compose.patroni.yml | /opt/mvn-reserve:docker-compose.patroni.yml) ;;
  *) fail "logical restore drill target is not one of the reviewed Patroni nodes" ;;
esac
[[ "${DRILL_ROOT}" == "${EXPECTED_DRILL_ROOT}" ]] ||
  fail "DRILL_ROOT must be the reviewed root-owned state directory"
[[ "${CLEANUP_SCRIPT}" == "${EXPECTED_CLEANUP_SCRIPT}" ]] ||
  fail "restore-drill cleanup helper path is not reviewed"
case "${EXPECTED_DATABASE_ROLE}" in
  primary) expected_in_recovery="f" ;;
  standby) expected_in_recovery="t" ;;
  *) fail "EXPECTED_DATABASE_ROLE must be primary or standby" ;;
esac
[[ -x "${CLEANUP_SCRIPT}" && ! -L "${CLEANUP_SCRIPT}" ]] ||
  fail "installed restore-drill cleanup helper is unavailable or unsafe"
[[ -x "${RUNTIME_CHECK_HELPER}" && ! -L "${RUNTIME_CHECK_HELPER}" ]] ||
  fail "installed PITR runtime attestation helper is unavailable or unsafe"
[[ -x "${RESOURCE_SIZING_HELPER}" && ! -L "${RESOURCE_SIZING_HELPER}" ]] ||
  fail "installed logical restore resource-sizing helper is unavailable or unsafe"
[[ -d "${PROJECT_DIR}" && ! -L "${PROJECT_DIR}" ]] ||
  fail "reviewed project directory is unavailable or unsafe"
[[ -f "${PROJECT_DIR}/${COMPOSE_FILE}" && ! -L "${PROJECT_DIR}/${COMPOSE_FILE}" ]] ||
  fail "reviewed Patroni compose file is unavailable or unsafe"
require_root_directory "${DRILL_ROOT}"

cd "${PROJECT_DIR}"
ensure_postgres_image
BACKEND_IMAGE="$(
  "${RUNTIME_CHECK_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --compose-file "${COMPOSE_FILE}" \
    --pitr-env-policy configured
)" || fail "PITR runtime attestation failed"
[[ -n "${BACKEND_IMAGE}" ]] || fail "PITR runtime attestation returned no backend image"
export BACKEND_IMAGE
COMPOSE=(docker compose -f "${COMPOSE_FILE}")

database_state="$(
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc \
    'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -AtF "|" -qc "SELECT pg_is_in_recovery(), pg_database_size(current_database())"'
)" || fail "could not prove live PostgreSQL role and size"
[[ "${database_state}" != *$'\n'* ]] || fail "live PostgreSQL state is ambiguous"
IFS='|' read -r in_recovery live_database_bytes unexpected_database_state <<<"${database_state}"
[[ "${in_recovery}" == "${expected_in_recovery}" ]] ||
  fail "live PostgreSQL role does not match the topology-proven restore target"
[[ "${live_database_bytes}" =~ ^[1-9][0-9]*$ && -z "${unexpected_database_state}" ]] ||
  fail "live PostgreSQL size attestation is invalid"

run_id="${PITR_OPERATION_ID}"
drill_dir="${DRILL_ROOT}/${run_id}"
container="mvn-logical-restore-${run_id}"
download_container="mvn-logical-restore-download-${run_id}"
download_path=""
sql_path="${drill_dir}/restore.sql"
normalized_sql="${drill_dir}/restore.normalized.sql"
credentials_file="${drill_dir}/container.env"

[[ ! -e "${drill_dir}" && ! -L "${drill_dir}" ]] ||
  fail "logical restore-drill operation directory already exists"
mkdir -- "${drill_dir}"
chmod 0700 "${drill_dir}"
require_root_directory "${drill_dir}"

cleanup() {
  local original_status=$?
  local cleanup_status=0
  trap - EXIT
  set +e
  "${CLEANUP_SCRIPT}" || cleanup_status=$?
  if (( cleanup_status != 0 && original_status == 0 )); then
    exit "${cleanup_status}"
  fi
  exit "${original_status}"
}
trap cleanup EXIT

db_container="$("${COMPOSE[@]}" ps -q "${DB_SERVICE}")"
[[ -n "${db_container}" ]] || fail "managed PostgreSQL container is not running"

mapfile -t db_env < <(
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc \
    'printf "%s\n%s\n" "$POSTGRES_USER" "${POSTGRES_DB:-air_conditioners}"'
)
POSTGRES_USER="${db_env[0]:-}"
POSTGRES_DB="${db_env[1]:-}"
[[ -n "${POSTGRES_USER}" && -n "${POSTGRES_DB}" ]] ||
  fail "could not read PostgreSQL user/database identity"

log "downloading the newest logical database backup through the attested app image"
"${COMPOSE[@]}" run -T --rm \
  --name "${download_container}" \
  --label com.mvn.purpose=api-restore-drill \
  --label "com.mvn.pitr.operation=${run_id}" \
  --volume "${drill_dir}:/restore-drill:rw" \
  "${APP_SERVICE}" python - <<'PY'
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from services.backup_service import backup_service
from services.google_service import get_google_service


MAX_DOWNLOAD_BYTES = 2 * 1024**3
DOWNLOAD_CHUNK_BYTES = 4 * 1024**2


class BoundedFile:
    def __init__(self, raw, maximum):
        self.raw = raw
        self.maximum = maximum

    def write(self, payload):
        end = self.raw.tell() + len(payload)
        if end > self.maximum:
            raise RuntimeError("logical backup download exceeds the reviewed bound")
        return self.raw.write(payload)

    def seek(self, offset, whence=os.SEEK_SET):
        position = self.raw.seek(offset, whence)
        if position < 0 or position > self.maximum:
            raise RuntimeError("logical backup downloader attempted an invalid seek")
        return position

    def tell(self):
        return self.raw.tell()

    def flush(self):
        return self.raw.flush()


items = backup_service.list_backups(limit=100)
latest = next((item for item in items if item.get("kind") == "db"), None)
if not isinstance(latest, dict):
    raise SystemExit("No logical database backups found")

name = str(latest.get("name") or "")
file_id = str(latest.get("id") or "")
created_at = latest.get("created_at")
size_bytes = latest.get("size_bytes")
if Path(name).name != name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\.sql(?:\.gz)?", name):
    raise SystemExit("Newest logical database backup has an unsafe filename")
if not file_id or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for character in file_id):
    raise SystemExit("Newest logical database backup has an invalid file id")
if not isinstance(size_bytes, int) or size_bytes < 1024 or size_bytes > MAX_DOWNLOAD_BYTES:
    raise SystemExit("Newest logical database backup has an invalid size")
if not isinstance(created_at, datetime):
    raise SystemExit("Newest logical database backup has no canonical creation time")
if created_at.tzinfo is None:
    created_at = created_at.replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
created_at = created_at.astimezone(timezone.utc)
if created_at > now + timedelta(minutes=5) or now - created_at > timedelta(hours=36):
    raise SystemExit("Newest logical database backup is outside the reviewed freshness window")

google_service = get_google_service()
credentials = google_service._require_credentials()
drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
remote = drive.files().get(
    fileId=file_id,
    fields="id,name,size,createdTime,md5Checksum,trashed",
).execute()
if not isinstance(remote, dict) or remote.get("trashed") is not False:
    raise SystemExit("Newest logical database backup metadata is invalid")
try:
    remote_size = int(remote.get("size"))
except (TypeError, ValueError):
    raise SystemExit("Newest logical database backup remote size is invalid")
remote_md5 = str(remote.get("md5Checksum") or "").lower()
if (
    str(remote.get("id") or "") != file_id
    or str(remote.get("name") or "") != name
    or remote_size != size_bytes
    or not re.fullmatch(r"[0-9a-f]{32}", remote_md5)
):
    raise SystemExit("Newest logical database backup changed before download")

destination = Path("/restore-drill/latest.sql.gz" if name.endswith(".sql.gz") else "/restore-drill/latest.sql")
flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
descriptor = os.open(destination, flags, 0o600)
try:
    with os.fdopen(descriptor, "r+b", buffering=0, closefd=False) as raw:
        bounded = BoundedFile(raw, min(size_bytes, MAX_DOWNLOAD_BYTES))
        request = drive.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(
            bounded,
            request,
            chunksize=DOWNLOAD_CHUNK_BYTES,
        )
        done = False
        while not done:
            _, done = downloader.next_chunk(num_retries=3)
        bounded.flush()
        os.fsync(descriptor)
finally:
    os.close(descriptor)

actual_size = destination.stat().st_size
hasher = hashlib.md5(usedforsecurity=False)
with destination.open("rb") as downloaded:
    while chunk := downloaded.read(1024 * 1024):
        hasher.update(chunk)
if actual_size != size_bytes or hasher.hexdigest() != remote_md5:
    destination.unlink(missing_ok=True)
    raise SystemExit("Downloaded logical database backup does not match remote metadata")
print(f"backup_name={name}")
print(f"backup_created_at={created_at.strftime('%Y-%m-%dT%H:%M:%SZ')}")
print(f"backup_size_bytes={size_bytes}")
print(f"backup_md5={remote_md5}")
print(f"downloaded_file={destination.name}")
PY

if [[ -f "${drill_dir}/latest.sql.gz" && ! -L "${drill_dir}/latest.sql.gz" ]]; then
  download_path="${drill_dir}/latest.sql.gz"
elif [[ -f "${drill_dir}/latest.sql" && ! -L "${drill_dir}/latest.sql" ]]; then
  download_path="${drill_dir}/latest.sql"
else
  fail "downloaded logical database backup is missing or unsafe"
fi

metadata="$(stat -Lc '%u:%g:%a:%h:%s' "${download_path}" 2>/dev/null || true)"
[[ ! -L "${download_path}" && -f "${download_path}" && "${metadata}" =~ ^0:0:[0-7]{3}:1:[1-9][0-9]*$ ]] ||
  fail "downloaded logical restore artifact metadata is unsafe"

# Decode through bounded descriptors.  The two-times free-space reservation is
# intentional: normalization below briefly needs a second full SQL file.
/usr/bin/python3 -I - "${download_path}" "${sql_path}" "${MAX_RESTORED_SQL_BYTES}" <<'PY'
import gzip
import os
import stat
import sys
from pathlib import Path


source = Path(sys.argv[1])
destination = Path(sys.argv[2])
maximum = int(sys.argv[3])
source_metadata = source.lstat()
if (
    source.is_symlink()
    or not stat.S_ISREG(source_metadata.st_mode)
    or source_metadata.st_uid != 0
    or source_metadata.st_gid != 0
    or source_metadata.st_nlink != 1
):
    raise SystemExit("downloaded logical backup metadata is unsafe")
if destination.exists() or destination.is_symlink():
    raise SystemExit("logical restore SQL destination already exists")
available = os.statvfs(destination.parent).f_bavail * os.statvfs(destination.parent).f_frsize
reserve = 1024**3
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
output_fd = os.open(destination, flags, 0o600)
total = 0
try:
    raw = source.open("rb")
    stream = gzip.GzipFile(fileobj=raw) if source.name.endswith(".gz") else raw
    try:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum or total * 2 + reserve > available:
                raise RuntimeError("logical backup expansion exceeds size or free-space bounds")
            view = memoryview(chunk)
            offset = 0
            while offset < len(view):
                written = os.write(output_fd, view[offset:])
                if written <= 0:
                    raise RuntimeError("logical backup expansion made no progress")
                offset += written
    finally:
        stream.close()
        if stream is not raw:
            raw.close()
    if total < 1024:
        raise RuntimeError("expanded logical backup is unexpectedly small")
    os.fchmod(output_fd, 0o600)
    os.fsync(output_fd)
except BaseException:
    os.close(output_fd)
    destination.unlink(missing_ok=True)
    raise
else:
    os.close(output_fd)
PY

metadata="$(stat -Lc '%u:%g:%a:%h:%s' "${sql_path}" 2>/dev/null || true)"
[[ ! -L "${sql_path}" && -f "${sql_path}" && "${metadata}" =~ ^0:0:600:1:[1-9][0-9]*$ ]] ||
  fail "expanded logical restore SQL metadata is unsafe"

sed '/^SET transaction_timeout = .*;$/d' "${sql_path}" >"${normalized_sql}"
[[ -s "${normalized_sql}" && ! -L "${normalized_sql}" ]] ||
  fail "normalized logical database backup is empty or unsafe"
mv -f -- "${normalized_sql}" "${sql_path}"

sql_bytes="$(stat -Lc '%s' "${sql_path}" 2>/dev/null || true)"
docker_memory_bytes="$(docker info --format '{{.MemTotal}}')" ||
  fail "could not inspect Docker host memory capacity"
[[ "${sql_bytes}" =~ ^[1-9][0-9]*$ && "${docker_memory_bytes}" =~ ^[1-9][0-9]*$ ]] ||
  fail "logical restore host memory capacity is invalid"
resource_envelope="$(
  /usr/bin/python3 -I "${RESOURCE_SIZING_HELPER}" \
    --sql-bytes "${sql_bytes}" \
    --live-database-bytes "${live_database_bytes}" \
    --host-total-bytes "${docker_memory_bytes}"
)" || fail "logical restore does not fit the reviewed primary-host resource envelope"
[[ "${resource_envelope}" != *$'\n'* ]] ||
  fail "logical restore resource-sizing output is ambiguous"
IFS=$'\t' read -r POSTGRES_DATA_TMPFS_BYTES POSTGRES_MEMORY_BYTES \
  POSTGRES_HOST_RESERVE_BYTES POSTGRES_REQUIRED_HOST_MEMORY_BYTES \
  POSTGRES_PRIMARY_MEMORY_LIMIT_BYTES unexpected_resource_field <<<"${resource_envelope}"
for resource_value in \
  "${POSTGRES_DATA_TMPFS_BYTES}" \
  "${POSTGRES_MEMORY_BYTES}" \
  "${POSTGRES_HOST_RESERVE_BYTES}" \
  "${POSTGRES_REQUIRED_HOST_MEMORY_BYTES}" \
  "${POSTGRES_PRIMARY_MEMORY_LIMIT_BYTES}"; do
  [[ "${resource_value}" =~ ^[1-9][0-9]*$ ]] ||
    fail "logical restore resource-sizing output is invalid"
done
[[ -z "${unexpected_resource_field}" ]] ||
  fail "logical restore resource-sizing output is ambiguous"

check_available_memory() {
  local host_available_kib=""
  local host_available_bytes=0
  host_available_kib="$(awk '$1 == "MemAvailable:" {print $2}' /proc/meminfo)"
  [[ "${host_available_kib}" =~ ^[1-9][0-9]*$ ]] ||
    fail "logical restore host available memory is invalid"
  host_available_bytes=$((host_available_kib * 1024))
  (( host_available_bytes >= POSTGRES_REQUIRED_HOST_MEMORY_BYTES )) ||
    fail "logical restore host has insufficient currently available memory"
}

check_available_memory
log "resource_envelope sql_bytes=${sql_bytes} live_database_bytes=${live_database_bytes} data_tmpfs_bytes=${POSTGRES_DATA_TMPFS_BYTES} container_memory_bytes=${POSTGRES_MEMORY_BYTES} host_reserve_bytes=${POSTGRES_HOST_RESERVE_BYTES}"

/usr/bin/python3 -I - "${credentials_file}" "${POSTGRES_USER}" "${POSTGRES_DB}" <<'PY'
import os
import secrets
import sys
from pathlib import Path


path = Path(sys.argv[1])
user, database = sys.argv[2:]
if not user or not database or any(character in "\r\n\0" for character in user + database):
    raise SystemExit("PostgreSQL drill identity is invalid")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
descriptor = os.open(path, flags, 0o600)
payload = (
    f"POSTGRES_USER={user}\n"
    f"POSTGRES_DB={database}\n"
    f"POSTGRES_PASSWORD={secrets.token_urlsafe(48)}\n"
).encode()
try:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise RuntimeError("could not write drill-only credential file")
        offset += written
    os.fchmod(descriptor, 0o600)
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
[[ ! -L "${credentials_file}" && "$(stat -Lc '%u:%g:%a:%h' "${credentials_file}" 2>/dev/null || true)" == "0:0:600:1" ]] ||
  fail "drill-only credential file metadata is unsafe"

log "starting a network-isolated disposable PostgreSQL container"
existing_container="$(docker ps -aq --filter "name=^/${container}$")" ||
  fail "could not inventory the logical restore container name"
[[ -z "${existing_container}" ]] ||
  fail "logical restore runtime name is already in use"
# Downloading and normalization can change page-cache pressure.  Re-check the
# exact available-memory gate immediately before Docker creates the cgroup.
check_available_memory
docker run --pull never -d \
  --name "${container}" \
  --label com.mvn.purpose=api-restore-drill \
  --label "com.mvn.pitr.operation=${run_id}" \
  --network none \
  --read-only \
  --cap-drop ALL \
  --cap-add CHOWN \
  --cap-add DAC_OVERRIDE \
  --cap-add FOWNER \
  --cap-add SETGID \
  --cap-add SETUID \
  --security-opt no-new-privileges:true \
  --pids-limit 256 \
  --memory "${POSTGRES_MEMORY_BYTES}" \
  --memory-swap "${POSTGRES_MEMORY_BYTES}" \
  --cpus 2.0 \
  --shm-size 256m \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m \
  --tmpfs /var/run/postgresql:rw,nosuid,nodev,size=16m \
  --tmpfs "/var/lib/postgresql/data:rw,nosuid,nodev,size=${POSTGRES_DATA_TMPFS_BYTES},uid=${POSTGRES_CONTAINER_UID},gid=${POSTGRES_CONTAINER_GID},mode=0700" \
  --mount "type=bind,source=${sql_path},target=/restore-input.sql,readonly" \
  --env-file "${credentials_file}" \
  "${POSTGRES_IMAGE}" >/dev/null
container_inspect_json="$(docker inspect "${container}")" ||
  fail "could not inspect the logical restore container"
CONTAINER_INSPECT_JSON="${container_inspect_json}" /usr/bin/python3 -I - \
  "${run_id}" "${POSTGRES_DATA_TMPFS_BYTES}" "${POSTGRES_MEMORY_BYTES}" \
  "${POSTGRES_CONTAINER_UID}" "${POSTGRES_CONTAINER_GID}" "${sql_path}" <<'PY'
import json
import os
import sys


operation_id, size, memory, uid, gid, sql_path = sys.argv[1:]
payload = json.loads(os.environ.pop("CONTAINER_INSPECT_JSON", ""))
if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
    raise SystemExit("logical restore container inspection is invalid")
container = payload[0]
config = container.get("Config")
host = container.get("HostConfig")
if not isinstance(config, dict) or not isinstance(host, dict):
    raise SystemExit("logical restore container contract is missing")
labels = config.get("Labels")
if not isinstance(labels, dict) or labels.get("com.mvn.purpose") != "api-restore-drill" or labels.get("com.mvn.pitr.operation") != operation_id:
    raise SystemExit("logical restore container labels are invalid")
if host.get("NetworkMode") != "none" or host.get("ReadonlyRootfs") is not True:
    raise SystemExit("logical restore container isolation is invalid")
if host.get("Memory") != int(memory) or host.get("MemorySwap") != int(memory):
    raise SystemExit("logical restore container memory envelope is invalid")
tmpfs = host.get("Tmpfs")
if not isinstance(tmpfs, dict):
    raise SystemExit("logical restore tmpfs contract is missing")
data_options = tmpfs.get("/var/lib/postgresql/data")
if not isinstance(data_options, str):
    raise SystemExit("logical restore data tmpfs is missing")
if set(data_options.split(",")) != {
    "rw",
    "nosuid",
    "nodev",
    f"size={size}",
    f"uid={uid}",
    f"gid={gid}",
    "mode=0700",
}:
    raise SystemExit("logical restore data tmpfs quota is invalid")
mounts = container.get("Mounts")
if not isinstance(mounts, list):
    raise SystemExit("logical restore input mount contract is missing")
binds = [mount for mount in mounts if isinstance(mount, dict) and mount.get("Type") == "bind"]
if len(binds) != 1 or binds[0].get("Source") != sql_path or binds[0].get("Destination") != "/restore-input.sql" or binds[0].get("RW") is not False:
    raise SystemExit("logical restore input must be the exact read-only SQL bind")
PY
log "drill_container=${container} data_tmpfs_bytes=${POSTGRES_DATA_TMPFS_BYTES} operation_id=${run_id}"

ready_streak=0
for _ in $(seq 1 90); do
  if docker exec "${container}" psql -Atqc "SELECT 1" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" 2>/dev/null | grep -Fxq 1; then
    ready_streak=$((ready_streak + 1))
    if (( ready_streak >= 3 )); then
      break
    fi
  else
    ready_streak=0
  fi
  sleep 1
done

if (( ready_streak < 3 )); then
  docker logs --tail=160 "${container}" || true
  fail "disposable PostgreSQL did not become SQL-ready"
fi

log "restoring the logical backup into the disposable PostgreSQL container"
restore_status=0
(
  ulimit -f 4096
  /usr/bin/timeout --foreground --signal=TERM --kill-after=30s "${RESTORE_TIMEOUT_SECONDS}s" \
    docker exec "${container}" \
    psql -q -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -f /restore-input.sql \
    >"${drill_dir}/restore.log" 2>&1
) || restore_status=$?
if (( restore_status != 0 )); then
  if ! /usr/bin/timeout --signal=KILL 30s docker stop --time 10 "${container}" >/dev/null 2>&1; then
    /usr/bin/timeout --signal=KILL 15s docker kill "${container}" >/dev/null 2>&1 || true
  fi
  tail -n 120 "${drill_dir}/restore.log" || true
  fail "logical restore failed or exceeded its wall-clock replay limit (status=${restore_status})"
fi

tables_count="$(
  docker exec "${container}" psql -Atqc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
)"
[[ "${tables_count}" =~ ^[0-9]+$ ]] || fail "logical restore returned an invalid table count"
(( tables_count >= MIN_PUBLIC_TABLES )) ||
  fail "logical restore produced too few public tables: ${tables_count}"
log "public_tables=${tables_count}"

business_counts="$(
  docker exec "${container}" psql -AtF '|' \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c 'SELECT (SELECT count(*) FROM product), (SELECT count(*) FROM payment), (SELECT count(*) FROM "order");'
)"
IFS='|' read -r product_count payment_count order_count unexpected_count <<<"${business_counts}"
for count in "${product_count}" "${payment_count}" "${order_count}"; do
  [[ "${count}" =~ ^[0-9]+$ ]] || fail "logical restore returned invalid business counts"
done
[[ -z "${unexpected_count}" ]] || fail "logical restore returned an ambiguous business count row"
log "product_count=${product_count} payment_count=${payment_count} order_count=${order_count}"
(( product_count >= 1 && order_count >= 1 )) ||
  fail "logical restore is missing required product/order data"

log "restore drill passed; live primary and standby databases were not modified"
