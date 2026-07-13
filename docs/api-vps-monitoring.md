# API VPS Monitoring Runbook

This repo keeps API VPS monitoring cheap and explicit: one script checks public
API health from anywhere, then optionally checks the host over SSH when a trusted
runner has access. The checks are read-only and are designed not to print env
values, private keys, tokens, database passwords, or Google credentials.

## What Is Checked

`scripts/check_api_vps_health.sh` always checks these public endpoints:

```bash
https://api.mvn.by/api/health
https://api.mvn.by/api/v1/products?limit=5
https://api.mvn.by/api/v1/filters/config
```

When `API_SSH_HOST` and `API_SSH_USER` are provided, it also checks the VPS:

- root disk and inode usage;
- `docker compose ps` for `/opt/air-api/docker-compose.prod.yml`;
- `app`, `bot`, and `db` containers are running;
- `pg_isready` inside the `db` container;
- localhost app health at `http://127.0.0.1:8000/api/health`;
- nginx origin certificate expiry on `127.0.0.1:443` with SNI `api.mvn.by`;
- latest Google Drive DB and media backups from inside the `app` container.

Backup freshness uses the existing app credentials mounted in production. Do not
copy Drive secrets to a local machine or GitHub workflow just to run this check.
Default freshness threshold is `BACKUP_MAX_AGE_HOURS=36`, which leaves room for
the daily 03:00 backup job plus normal operational delay.

## Manual Commands

Public-only check from any machine:

```bash
bash scripts/check_api_vps_health.sh --public-only
```

Full check from a machine that can SSH to the API VPS:

```bash
API_SSH_HOST=mvn-api \
API_SSH_USER=root \
bash scripts/check_api_vps_health.sh
```

Full check with an explicit key path:

```bash
API_SSH_HOST=185.250.45.54 \
API_SSH_USER=root \
API_SSH_KEY_PATH=~/.ssh/id_ed25519 \
bash scripts/check_api_vps_health.sh
```

Tighter or looser backup threshold:

```bash
API_SSH_HOST=mvn-api \
API_SSH_USER=root \
BACKUP_MAX_AGE_HOURS=48 \
bash scripts/check_api_vps_health.sh
```

Temporarily skip backup freshness during a known Google Drive auth incident:

```bash
API_SSH_HOST=mvn-api \
API_SSH_USER=root \
CHECK_BACKUPS=false \
bash scripts/check_api_vps_health.sh
```

Backup freshness can also be inspected manually on the VPS without exposing
Drive secrets:

```bash
ssh mvn-api
cd /opt/air-api
docker compose -f docker-compose.prod.yml exec -T app python3 - <<'PY'
from datetime import datetime, timezone
from services.backup_service import backup_service

items = backup_service.list_backups(limit=100)
now = datetime.now(timezone.utc)
for kind in ("db", "media"):
    latest = next((item for item in items if item.get("kind") == kind), None)
    if latest is None:
        print(f"{kind}: missing")
        continue
    created_at = latest["created_at"]
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = (now - created_at).total_seconds() / 3600
    print(f"{kind}: {created_at.isoformat()} age_hours={age_hours:.1f} name={latest['name']}")
PY
```

## Cron Examples

Public check every 5 minutes from any small external box:

```cron
*/5 * * * * cd /path/to/air-api && bash scripts/check_api_vps_health.sh --public-only >> /var/log/mvn-api-health.log 2>&1
```

Full hourly check from a trusted runner with SSH access:

```cron
7 * * * * cd /path/to/air-api && API_SSH_HOST=mvn-api API_SSH_USER=root bash scripts/check_api_vps_health.sh >> /var/log/mvn-api-vps-health.log 2>&1
```

Cron can route failures through `MAILTO`, a local MTA, or a webhook wrapper. Keep
webhook URLs and bot tokens in the runner environment or secret store, and never
echo them from the monitor command.

## GitHub Actions

Use the manual **API VPS Health Check** workflow for ad hoc checks from GitHub.
It has two modes:

- `public-only`: no SSH secrets needed; validates the public API.
- `ssh`: uses existing `SSH_HOST_API`, `SSH_USER_API`, and `SSH_KEY` secrets and
  runs the full host and backup freshness checks.

This workflow is intentionally manual-only to avoid noisy failures until the
owner chooses an alerting policy. If scheduled Actions alerts are desired, add a
cron schedule to the workflow and route failed workflow notifications to the
owner's chosen channel.

## Alert Routing Options

Pick one primary owner-visible channel and one fallback:

- GitHub Actions failure notifications for the manual or future scheduled
  workflow.
- Cron `MAILTO` to an operations mailbox.
- A small wrapper that posts only failure summaries to Telegram, Slack, Discord,
  or another webhook.
- Uptime-style public checks from a separate VPS if a second cheap host exists.

Alert payloads should include the failing check names and timestamps, not env
dumps, private keys, Drive folder IDs, tokens, or database connection strings.

## Failure Triage

Public `/api/health` fails:

```bash
ssh mvn-api
cd /opt/air-api
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=120 app
systemctl status nginx --no-pager
```

Products or filters config fail while health is green:

```bash
ssh mvn-api
cd /opt/air-api
docker compose -f docker-compose.prod.yml logs --tail=120 app
docker compose -f docker-compose.prod.yml exec -T db sh -lc 'pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

SSH host checks fail:

```bash
ssh -o BatchMode=yes mvn-api true
```

If SSH fails only from GitHub Actions, treat it as network/firewall/key reachability
first, not as an API application failure.

Disk or inode usage is critical:

```bash
ssh mvn-api
df -h /
df -ih /
docker system df
journalctl --disk-usage
```

Do cleanup only after identifying the large files or Docker layers. Avoid broad
deletes during an incident.

Container or DB readiness fails:

```bash
ssh mvn-api
cd /opt/air-api
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=120 db app bot
```

TLS expiry warns or fails:

```bash
ssh mvn-api
certbot certificates
certbot renew --dry-run
nginx -t
```

Backup freshness fails:

```bash
ssh mvn-api
cd /opt/air-api
docker compose -f docker-compose.prod.yml logs --tail=200 app | grep -i backup
docker compose -f docker-compose.prod.yml exec -T app python3 - <<'PY'
from services.backup_service import backup_service
print(len(backup_service.list_backups(limit=100)))
PY
```

Check that production still has `ENVIRONMENT=production`, `BACKUP_FOLDER_ID`,
and the directory-backed OAuth token contract described in
[`google-oauth-token-runbook.md`](google-oauth-token-runbook.md). The token must
resolve to `/app/google-oauth/token.json`; do not restore the old single-file
bind mount.
Trigger a manual backup only after the owner approves a state-changing action.

## Safety Notes

- The monitor does not run `docker compose config`, because that can expand env
  values into logs.
- The monitor does not SSH unless `API_SSH_HOST` and `API_SSH_USER` are set.
- The backup freshness check runs inside the existing `app` container and prints
  only backup kind, age, creation time, and filename.
- Public-only mode is safe for external cron and does not require production
  credentials.
