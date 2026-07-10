# API Single-VPS Migration Runbook

Owner/operator runbook for moving `api.mvn.by` from the current single API VPS to a new single API VPS.

Related source material:

- [Deployment guide](deployment.md)
- [`docker-compose.prod.yml`](../docker-compose.prod.yml)
- [Backend deploy workflow](../.github/workflows/deploy.yml)
- [`scripts/deploy.sh`](../scripts/deploy.sh)
- [`scripts/post_deploy_smoke_check.sh`](../scripts/post_deploy_smoke_check.sh)
- [`services/backup_service.py`](../services/backup_service.py)
- [`scripts/restore_db.py`](../scripts/restore_db.py)

## Scope And Safety

This runbook is for one production API origin running Docker Compose services:

- `db`: PostgreSQL
- `app`: FastAPI, static/media serving, manager UI, and in-process scheduler loops
- `bot`: Telegram bot polling process

Current production assumptions:

- Production directory: `/opt/air-api`
- Public API domain: `api.mvn.by`
- Current old API IP from existing docs: `185.250.45.54`
- Public access goes through Cloudflare/nginx to `127.0.0.1:8000`
- Compose binds Postgres and FastAPI to localhost on the VPS

Hard safety rules:

- Do not run two active `bot` services against the same bot token.
- Do not run two active primary `app` services. A passive standby `app` is allowed only with `APP_ROLE=standby`, scheduler disabled, and no bot polling.
- During cutover, stop old `app` and `bot` before promoting the new production `app`.
- Start the new `bot` only after the new `app` has passed app-only and public smoke checks.
- If rollback is needed, stop new `app` and `bot` before restarting old `app` and `bot`.

Runtime role controls:

| Host mode | Services | Required env | Expected startup logs |
| --- | --- | --- | --- |
| Primary/current production | `db`, `app`, `bot` | `APP_ROLE=primary` or unset; `SCHEDULER_ENABLED`/`BOT_ENABLED` unset or `true` | `Scheduler startup enabled`; `Starting bot polling` |
| Standby/passive API | `db`, `app` only | `APP_ROLE=standby`, `SCHEDULER_ENABLED=false`, `BOT_ENABLED=false` | `Scheduler startup skipped`; no bot polling |

Unset or empty runtime env values follow `APP_ROLE`, and missing `APP_ROLE`
defaults to `primary` for current production compatibility. `SCHEDULER_ENABLED`
and `BOT_ENABLED` are explicit overrides. If they are set to `false`, they keep
the scheduler or bot disabled even when `APP_ROLE=primary`. Remove the override
or set it to `true` before promotion. If a standby `bot` container is
accidentally started while `BOT_ENABLED=false` or `APP_ROLE=standby`, it stays
idle without Telegram polling so Compose `restart: always` does not create a
restart loop.

These controls do not enable Cloudflare load balancing, automatic failover, or
public standby cutover. Do not route public write traffic to a standby host.

Passive standby verification is app-only and must not change Cloudflare, DNS, or
load balancing:

```bash
ssh "${API_USER}@${NEW_API_HOST}"
cd /opt/air-api
printf '\nAPP_ROLE=standby\nSCHEDULER_ENABLED=false\nBOT_ENABLED=false\n' >> .env
docker compose -f docker-compose.prod.yml up -d db app
docker compose -f docker-compose.prod.yml stop bot || true
docker compose -f docker-compose.prod.yml logs --tail=120 app | grep 'Scheduler startup skipped'
curl -fsS http://127.0.0.1:8000/api/health
```

Use full `scripts/check_api_vps_health.sh` only for the primary host because it
expects `app`, `bot`, and `db` to be running. For standby, use public/app-only
health checks against the standby origin.

## Variables

Set these on the operator workstation before running local transfer commands:

```bash
OLD_API_HOST=185.250.45.54
NEW_API_HOST=<new-vps-ip>
API_USER=root
MIGRATION_ID=api-migration-$(date +%Y%m%d%H%M%S)
WORKDIR="$HOME/$MIGRATION_ID"
COMMIT_SHA=<deployed-backend-commit-sha>
IMAGE="ghcr.io/mvnby/air-api/backend:${COMMIT_SHA}"
```

Use a commit SHA that has already passed CI and was built by GitHub Actions. The
deploy workflow publishes only:

```text
ghcr.io/mvnby/air-api/backend:<commit-sha>
```

The immutable SHA tag is mandatory so the old and new hosts run the same known
image.

## Phase 1: Preflight Inventory

Run inventory commands on the old API VPS. These commands avoid printing secret values.

```bash
ssh "${API_USER}@${OLD_API_HOST}"
cd /opt/air-api
```

Confirm compose services and images:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml images
docker compose -f docker-compose.prod.yml config --services
```

Record `.env` key names without values:

```bash
awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $1"=<redacted>"}' .env | sort
```

Confirm required runtime files exist:

```bash
for f in .env docker-compose.prod.yml token.json client_secret.json credentials.json; do
  if [ -f "$f" ]; then
    stat -c '%n %s bytes mode=%a owner=%U:%G' "$f"
  else
    echo "MISSING $f"
  fi
done
```

Inventory media and local backup directories:

```bash
du -sh media backups 2>/dev/null || true
find media -type f | wc -l
find backups -maxdepth 1 -type f -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort | tail -20
```

Inventory Postgres volume and DB size:

```bash
docker volume ls | grep postgres || true
docker compose -f docker-compose.prod.yml exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select pg_size_pretty(pg_database_size(current_database())) as db_size;"'
```

Inventory Google Drive backup visibility from the app container:

```bash
docker compose -f docker-compose.prod.yml exec -T app python scripts/restore_db.py --list
```

This confirms `token.json` is usable and shows available DB/media backups. Do not use Drive backups as the primary migration source unless a direct frozen dump cannot be used; a fresh dump taken after the maintenance freeze is the least stale source of truth.

## Phase 2: New VPS Baseline

Prepare the new VPS before the maintenance window. Do not start production `app` or `bot` yet.

Install baseline packages:

```bash
ssh "${API_USER}@${NEW_API_HOST}"
apt-get update
apt-get install -y ca-certificates curl gnupg nginx certbot python3-certbot-dns-cloudflare
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker nginx
```

Configure the firewall to expose only SSH and HTTP(S):

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose
```

Create the application directory:

```bash
mkdir -p /opt/air-api
chmod 700 /opt/air-api
```

Set up nginx to proxy only to the localhost-bound app:

```bash
cat >/etc/nginx/sites-available/api.mvn.by <<'NGINX'
server {
    listen 80;
    server_name api.mvn.by;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/api.mvn.by /etc/nginx/sites-enabled/api.mvn.by
nginx -t
systemctl reload nginx
```

TLS options:

- Preferred: issue the certificate before DNS cutover with Cloudflare DNS-01, so `api.mvn.by` can be tested with `curl --resolve`.
- Acceptable: issue/refresh TLS immediately after DNS cutover if DNS-01 is not available, but keep the old VPS ready for rollback until HTTPS passes.

For DNS-01, keep the Cloudflare token file outside `/opt/air-api`, mode `600`, and do not print it in logs:

```bash
chmod 600 /root/cloudflare.ini
certbot certonly --dns-cloudflare --dns-cloudflare-credentials /root/cloudflare.ini -d api.mvn.by
```

Then update nginx for HTTPS:

```bash
cat >/etc/nginx/sites-available/api.mvn.by <<'NGINX'
server {
    listen 80;
    server_name api.mvn.by;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.mvn.by;

    ssl_certificate /etc/letsencrypt/live/api.mvn.by/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.mvn.by/privkey.pem;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX
nginx -t
systemctl reload nginx
```

## Phase 3: Stage Runtime Files

From the operator workstation, create a local migration directory:

```bash
mkdir -p "$WORKDIR"
chmod 700 "$WORKDIR"
```

Copy non-database runtime files from the old VPS without printing contents:

```bash
ssh "${API_USER}@${OLD_API_HOST}" '
  set -euo pipefail
  cd /opt/air-api
  install -m 700 -d /root/api-migration-stage
  tar -czf /root/api-migration-stage/runtime-files.tar.gz \
    .env docker-compose.prod.yml token.json client_secret.json credentials.json
  chmod 600 /root/api-migration-stage/runtime-files.tar.gz
'

scp "${API_USER}@${OLD_API_HOST}:/root/api-migration-stage/runtime-files.tar.gz" "$WORKDIR/"
scp "$WORKDIR/runtime-files.tar.gz" "${API_USER}@${NEW_API_HOST}:/root/"

ssh "${API_USER}@${NEW_API_HOST}" '
  set -euo pipefail
  cd /opt/air-api
  tar -xzf /root/runtime-files.tar.gz
  chmod 600 .env token.json client_secret.json credentials.json
'
```

Persist the SHA-pinned application release on the new VPS and keep a separate
cutover compose filename for the migration commands:

```bash
ssh "${API_USER}@${NEW_API_HOST}" "cd /opt/air-api && COMMIT_SHA='${COMMIT_SHA}' sh -s" <<'SH'
set -euo pipefail
test -n "${COMMIT_SHA}"
cp docker-compose.prod.yml docker-compose.cutover.yml
touch .env
tmp="$(mktemp .env.tmp.XXXXXX)"
grep -v '^BACKEND_IMAGE=' .env > "${tmp}" || true
printf 'BACKEND_IMAGE=ghcr.io/mvnby/air-api/backend:%s\n' "${COMMIT_SHA}" >> "${tmp}"
chmod --reference=.env "${tmp}" 2>/dev/null || chmod 600 "${tmp}"
chown --reference=.env "${tmp}" 2>/dev/null || true
mv "${tmp}" .env
docker compose -f docker-compose.cutover.yml config | grep 'image: ghcr.io/mvnby/air-api/backend:'
SH
```

Pull the pinned image and start only the database on the new VPS:

```bash
ssh "${API_USER}@${NEW_API_HOST}"
cd /opt/air-api
COMMIT_SHA=<deployed-backend-commit-sha>

read -rsp "GHCR token: " GHCR_PAT
printf '\n'
printf '%s' "$GHCR_PAT" | docker login ghcr.io -u <github-username> --password-stdin
unset GHCR_PAT

docker manifest inspect "ghcr.io/mvnby/air-api/backend:${COMMIT_SHA}" >/dev/null
docker compose -f docker-compose.cutover.yml pull app
docker compose -f docker-compose.cutover.yml up -d db
docker compose -f docker-compose.cutover.yml ps
```

Do not start `app` or `bot` yet.

If this host was previously used for passive standby verification, leave
`APP_ROLE=standby`, `SCHEDULER_ENABLED=false`, and `BOT_ENABLED=false` in place
until the maintenance freeze. Before Phase 7 promotion, flip them to primary
values as shown there.

## Phase 4: Freeze Old API

Schedule a maintenance window. The freeze starts when old `app` and `bot` are stopped.

Announce the freeze to stakeholders. During the freeze:

- Website/API writes are unavailable.
- Telegram bot is unavailable.
- No imports, manager edits, order changes, media uploads, or restore jobs should be started.

On the old VPS:

```bash
ssh "${API_USER}@${OLD_API_HOST}"
cd /opt/air-api
docker compose -f docker-compose.prod.yml stop bot app
docker compose -f docker-compose.prod.yml ps
```

Confirm old localhost app is down:

```bash
curl -fsS http://127.0.0.1:8000/api/health && echo "UNEXPECTED: old app still responds" || echo "old app stopped"
```

The old `db` remains running only long enough to take the final dump.

## Phase 5: Final DB And Media Backup

On the old VPS, create a final frozen DB dump and media archive:

```bash
cd /opt/air-api
install -m 700 -d /root/api-migration-final

docker compose -f docker-compose.prod.yml exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
  > /root/api-migration-final/db.sql

tar -C /opt/air-api -czf /root/api-migration-final/media.tar.gz media
chmod 600 /root/api-migration-final/db.sql /root/api-migration-final/media.tar.gz

ls -lh /root/api-migration-final/db.sql /root/api-migration-final/media.tar.gz
```

Optional but recommended: keep a Drive backup as a second recovery source. This can take longer because it uploads DB and media to Google Drive:

```bash
docker compose -f docker-compose.prod.yml run -T --rm app python -c \
  "from services.backup_service import backup_service; backup_service.perform_backup(cleanup=True)"
```

Only run this optional step if the longer maintenance window is acceptable. Use `docker compose run`, not `up -d app`, so the public old API and scheduler lifecycle do not restart during the freeze.

Transfer final artifacts to the new VPS:

```bash
scp "${API_USER}@${OLD_API_HOST}:/root/api-migration-final/db.sql" "$WORKDIR/"
scp "${API_USER}@${OLD_API_HOST}:/root/api-migration-final/media.tar.gz" "$WORKDIR/"
scp "$WORKDIR/db.sql" "$WORKDIR/media.tar.gz" "${API_USER}@${NEW_API_HOST}:/root/"
```

## Phase 6: Restore On New VPS

On the new VPS:

```bash
ssh "${API_USER}@${NEW_API_HOST}"
cd /opt/air-api
docker compose -f docker-compose.cutover.yml up -d db
```

Restore the DB dump:

```bash
docker compose -f docker-compose.cutover.yml exec -T db sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < /root/db.sql
```

Restore media:

```bash
rm -rf /opt/air-api/media
tar -C /opt/air-api -xzf /root/media.tar.gz
chown -R root:root /opt/air-api/media
```

Run migrations and required defaults with a one-off container. This does not start the long-running `app` service:

```bash
docker compose -f docker-compose.cutover.yml run -T --rm app alembic upgrade head
docker compose -f docker-compose.cutover.yml run -T --rm app python3 scripts/ensure_global_config_defaults.py
```

## Phase 7: App-Only Smoke On New VPS

At this point old `app` and old `bot` must still be stopped.

Promote the new host to primary before starting the long-running app. If standby
vars were added earlier, remove the explicit disables or set them to `true`:

```bash
cd /opt/air-api
python3 - <<'PY'
from pathlib import Path

path = Path(".env")
lines = path.read_text(encoding="utf-8").splitlines()
drop = {"APP_ROLE", "SCHEDULER_ENABLED", "BOT_ENABLED"}
kept = [line for line in lines if line.split("=", 1)[0].strip() not in drop]
kept.extend(["APP_ROLE=primary", "SCHEDULER_ENABLED=true", "BOT_ENABLED=true"])
path.write_text("\n".join(kept) + "\n", encoding="utf-8")
PY
```

Start the new app only:

```bash
docker compose -f docker-compose.cutover.yml up -d app
docker compose -f docker-compose.cutover.yml ps
docker compose -f docker-compose.cutover.yml logs --tail=120 app
docker compose -f docker-compose.cutover.yml logs --tail=120 app | grep 'Scheduler startup enabled'
```

Run local app smoke:

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/v1/products?limit=5
curl -fsS http://127.0.0.1:8000/api/v1/filters/config
```

Run nginx-origin smoke on the new VPS:

```bash
curl -fsS -H 'Host: api.mvn.by' http://127.0.0.1/api/health
```

If TLS was issued before DNS cutover, test from the operator workstation:

```bash
curl -fsS --resolve "api.mvn.by:443:${NEW_API_HOST}" https://api.mvn.by/api/health
curl -fsS --resolve "api.mvn.by:443:${NEW_API_HOST}" "https://api.mvn.by/api/v1/products?limit=5"
curl -fsS --resolve "api.mvn.by:443:${NEW_API_HOST}" https://api.mvn.by/api/v1/filters/config
```

Do not start `bot` yet.

## Phase 8: DNS And Deploy Target Cutover

In Cloudflare:

1. Update `api.mvn.by` A record from the old IP to `NEW_API_HOST`.
2. Keep the same proxy mode as the old record unless there is an explicit owner decision to change it.
3. If using Cloudflare proxied DNS, TTL is automatic. If DNS-only, use the previously agreed low TTL.

In GitHub repository secrets:

1. Update `SSH_HOST_API` to `NEW_API_HOST`.
2. Keep `SSH_USER_API` unchanged unless the new VPS uses a different deploy user.
3. Do not run a deployment until public smoke passes unless the deployment itself is part of the approved cutover.

After DNS starts resolving to the new origin, run public smoke from outside the VPS:

```bash
dig +short api.mvn.by
curl -fsS https://api.mvn.by/api/health
curl -fsS "https://api.mvn.by/api/v1/products?limit=5"
curl -fsS https://api.mvn.by/api/v1/filters/config
curl -fsS https://api.mvn.by/docs >/dev/null
```

If the public smoke is green, start the new bot:

```bash
ssh "${API_USER}@${NEW_API_HOST}" '
  set -euo pipefail
  cd /opt/air-api
  docker compose -f docker-compose.cutover.yml up -d bot
  docker compose -f docker-compose.cutover.yml ps
  docker compose -f docker-compose.cutover.yml logs --tail=120 bot
'
```

Run one final public smoke:

```bash
curl -fsS https://api.mvn.by/api/health
curl -fsS "https://api.mvn.by/api/v1/products?limit=5"
curl -fsS https://api.mvn.by/api/v1/filters/config
```

## Phase 9: Post-Cutover Normalization

The migration used `docker-compose.cutover.yml` with a SHA-pinned image. After the owner confirms the migration is stable, choose one of these paths:

- Keep using the SHA-pinned cutover compose until the next planned backend deploy.
- Run the GitHub backend deploy workflow from `main` after `SSH_HOST_API` is
  updated. The exact commit must already have successful CI. The workflow copies
  `docker-compose.prod.yml`, pulls only application images, runs
  migrations/defaults with `--no-deps`, recreates `app` and `bot` without
  touching PostgreSQL, and runs `scripts/post_deploy_smoke_check.sh`.

Cleanup after the rollback window:

```bash
ssh "${API_USER}@${OLD_API_HOST}" 'docker compose -f /opt/air-api/docker-compose.prod.yml ps'
ssh "${API_USER}@${NEW_API_HOST}" 'rm -f /root/db.sql /root/media.tar.gz /root/runtime-files.tar.gz'
rm -rf "$WORKDIR"
```

Do not delete old VPS data or backups until the owner explicitly accepts the migration and the rollback window has ended.

## Rollback

Use rollback if app-only smoke, public smoke, bot startup, or early production monitoring fails.

Critical order:

1. Stop new `bot` and `app`.
2. Point DNS back to the old IP.
3. Restart old `app` and `bot`.
4. Restore GitHub `SSH_HOST_API` to the old IP if it was changed.

Commands:

```bash
ssh "${API_USER}@${NEW_API_HOST}" '
  set -euo pipefail
  cd /opt/air-api
  docker compose -f docker-compose.cutover.yml stop bot app || true
  python3 - <<'"'"'PY'"'"'
from pathlib import Path

path = Path(".env")
lines = path.read_text(encoding="utf-8").splitlines()
drop = {"APP_ROLE", "SCHEDULER_ENABLED", "BOT_ENABLED"}
kept = [line for line in lines if line.split("=", 1)[0].strip() not in drop]
kept.extend(["APP_ROLE=standby", "SCHEDULER_ENABLED=false", "BOT_ENABLED=false"])
path.write_text("\n".join(kept) + "\n", encoding="utf-8")
PY
  docker compose -f docker-compose.cutover.yml ps
'
```

In Cloudflare, set `api.mvn.by` A record back to the old IP, for example `185.250.45.54`.

On the old VPS:

```bash
ssh "${API_USER}@${OLD_API_HOST}" '
  set -euo pipefail
  cd /opt/air-api
  docker compose -f docker-compose.prod.yml up -d app bot
  docker compose -f docker-compose.prod.yml ps
  curl -fsS http://127.0.0.1:8000/api/health
'
```

Public rollback smoke:

```bash
dig +short api.mvn.by
curl -fsS https://api.mvn.by/api/health
curl -fsS "https://api.mvn.by/api/v1/products?limit=5"
curl -fsS https://api.mvn.by/api/v1/filters/config
```

If the new API accepted writes, orders, imports, media uploads, or bot interactions before rollback, data may diverge. Decide whether to back-transfer a new dump/media archive from the new VPS to the old VPS before restarting old services, or accept losing those writes. The lowest-risk rollback is before the new bot starts and before ending the maintenance window.

## Final Owner Checklist

- Old and new VPS inventory captured.
- Maintenance window approved.
- `COMMIT_SHA` selected and confirmed available in GHCR.
- New VPS has Docker, Compose, nginx, firewall, and TLS ready.
- `/opt/air-api/.env`, compose, Google credential files, media, and final DB dump restored on new VPS.
- Old `app` and `bot` stopped before new `app` starts.
- If the new host was used as standby, `APP_ROLE=primary`, `SCHEDULER_ENABLED=true`, and `BOT_ENABLED=true` are set before promotion.
- New `app` logs `Scheduler startup enabled` during cutover.
- New `app` passes localhost and nginx-origin smoke.
- Cloudflare `api.mvn.by` points to new IP.
- GitHub `SSH_HOST_API` points to new IP.
- Public smoke passes.
- New `bot` starts only after public smoke passes.
- Rollback path remains available until the owner ends the rollback window.
