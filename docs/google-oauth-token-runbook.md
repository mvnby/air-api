# Google OAuth Token Persistence Runbook

## Contract

Google OAuth credentials must be stored in a writable directory mount, never as
an individual bind-mounted file. OAuth refresh persistence uses an atomic
temporary-file rename. Linux rejects that rename when the destination itself is
a bind-mount point (`EBUSY`).

All seven production/HA compose sources use this contract:

```text
host:      <project>/google-oauth/token.json
container: /app/google-oauth/token.json
env:       GOOGLE_TOKEN_FILE=/app/google-oauth/token.json
directory mode: 0700
token mode:     0600
```

The local `docker-compose.api.yml` follows the same rule. The former
`deploy_api.sh` source-bind deployment is retired because it changed live code
before smoke checks and could not provide a real rollback.

## Safe Preparation

The deployment scripts run this helper while holding the deployment lock and
before any migration or container activation:

```bash
GOOGLE_OAUTH_PROJECT_DIR=/opt/air-api \
  bash scripts/prepare_google_oauth_token_dir.sh prepare
```

It creates `google-oauth/` with mode `0700`, copies a valid legacy token to a
same-directory temporary file, sets mode `0600`, and atomically renames it to
`google-oauth/token.json`. It accepts both historical locations:

- `/opt/air-api/token.json`
- `/opt/mvn-reserve/secrets/token.json`

The helper never prints token contents and never deletes the legacy source. If
both historical files exist with different contents, deployment fails closed;
select the intended source explicitly with `GOOGLE_OAUTH_LEGACY_TOKEN_FILE`.

Read-only verification:

```bash
GOOGLE_OAUTH_PROJECT_DIR=/opt/air-api \
  bash scripts/prepare_google_oauth_token_dir.sh verify
```

## HA Rollout

Keep the current legacy token files through the complete proof and rollback
window.

1. Prepare both nodes without deleting or moving either legacy token.
   Every rollout uses a run-unique candidate compose. The deployment lock is
   held continuously across candidate activation, smoke checks, and the final
   atomic promotion, so concurrent deploys cannot overwrite or promote another
   run's candidate. Patroni migrations also use a run-unique candidate and do
   not replace the active compose on disk.
2. Deploy the fenced Patroni replica first. Confirm `/api/health` is healthy and
   `/api/ready` remains fenced with HTTP 503.
3. Deploy the primary through the blue-green path.
4. Confirm exactly one ready API origin and one scheduler owner.
5. Confirm the active container sees the directory-backed token without
   printing it:

   ```bash
   docker compose -f docker-compose.patroni.yml --profile bluegreen exec -T app-green \
     sh -lc 'test "$GOOGLE_TOKEN_FILE" = /app/google-oauth/token.json && test -f "$GOOGLE_TOKEN_FILE" && test -w "$GOOGLE_TOKEN_FILE"'
   ```

   Replace `app-green` with the service named by `.active-api-slot`.
6. Run the manual Google Drive restore drill and require a real backup selection,
   at least the expected table count, and non-zero product/order counts.
7. Check host metadata only: directory mode `700`, token mode `600`, token mtime
   advanced after refresh, and the legacy source still exists.
8. Re-run the Patroni production and PITR checks.

Do not delete the legacy token as part of this rollout. Retirement is a separate
manual cleanup after an agreed rollback window and repeated successful refresh,
backup, and restore-drill evidence.

## Rollback Policy

Before promotion, failure cleanup removes only that run's candidate; canonical
compose is still the legacy compose. The failure path force-recreates the
actually active API service (and `bot` where applicable) through canonical
compose before the workflow's guard runs. This preserves the exact pre-release
runtime; it does not claim that the already-known legacy Google defect is fixed.

After a successful atomic promotion, rollback to a pre-hotfix image is forbidden:
an unlabeled image cannot durably refresh through either mount contract. The
rollback helper accepts only images labeled
`org.mvn.google-oauth-token-contract=directory-v1`, validates the exact compose
environment and directory mount, proves an atomic same-directory write, requires
healthy durable credentials, and lists a real backup before declaring success.
For a pre-hotfix target, use a normal roll-forward release of the OAuth-aware
image. The preserved `<compose>.pre-google-oauth-dir` is diagnostic evidence, not
an approved automatic rollback input.
