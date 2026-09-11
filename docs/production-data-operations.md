# Production data operations

Read this guide before production data operations and the matching operation
runbook before executing it. Start with read-only reports; the execution gates
below remain mandatory. Deployment and HA procedures are in
[deployment](deployment.md) and [API HA](api-ha-runbook.md).

Production server intentionally runs from Docker images only (no git checkout in `/opt/air-api`).

1. Trigger path:
   - Backend deploy pulls immutable GHCR API images. Active Telegram polling is deployed separately; see [bot service boundary](bot-service-boundary.md).
   - Optional post-deploy ops run via `scripts/ops_post_deploy.sh`.
2. Safe defaults:
   - `OPS_MODE=report_only`
   - `RUN_NORMALIZE_LEGACY=false`
   - `RUN_BACKFILL_BRAND_SERIES=false`
   - `RUN_SAFE_BRAND_CLEANUP=false`
   - `RUN_CLEANUP_LEGACY_LINKS=false`
   - `RUN_REPORT_LEGACY_LINKS=true`
   - `DRY_RUN=true`
3. Manual commands on prod:
   - Report only:
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/report_legacy_tag_links.py`
   - Report CRM branch candidates (orders grouped by customer/address):
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/report_customer_branch_candidates.py --min-orders 2 --only-candidates`
   - CRM branch backfill dry-run (safe default):
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/backfill_customer_branches.py --min-orders 2`
   - CRM branch backfill execute (manual-only):
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/backfill_customer_branches.py --min-orders 2 --execute`
   - CRM branch backfill for one customer (recommended first run):
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/backfill_customer_branches.py --customer-id 123 --execute`
   - Tenant-scope historical report (primary-only):
     - Lead/Order: `python3 scripts/backfill_lead_order_tenant_scope.py --limit 1`
     - Customer/OCR: `python3 scripts/backfill_customer_tenant_scope.py --limit 1`
     - The production contract is complete. Both commands should report no
       candidates and `contract_ready=true`; do not execute them unless the
       schema was deliberately rolled back to the expand phase.
   - Shared catalog grant report (read-only plan):
     `python3 scripts/manage_shared_catalog_grant.py plan --manifest config/shared_catalog_grants/polotsk.json --desired-status active`
   - Shared catalog grant execution is manual-only: review the plan and run only
     its emitted, expiring `reviewed_execute_command`; repeat fresh plans until
     `complete=true`.
   - Tenant manager production plan/execute:
     use the manual `Provision Tenant Manager` GitHub workflow from an exact
     reviewed `main` SHA. Review its sanitized plan artifact, then execute with
     `apply=true`, the exact `plan_digest`, and the temporary protected
     `TENANT_MANAGER_ONE_TIME_PASSWORD` environment secret. Delete that secret
     immediately after the run; see [tenant manager provisioning](tenant-manager-provisioning.md).
   - Product media URL audit/plan (read-only default):
     `python3 scripts/manage_product_media_url_backfill.py plan --manifest config/product_media_url_backfills/polotsk-presentation-v1.json`
   - Product media URL execution is primary-only and manual-only. Resolve every
     manifest blocker, review the exact source hashes/locations, and run only
     the fresh plan's expiring `reviewed_execute_command`; see
     [product media URL backfill](product-media-url-backfill.md).
   - Normalize:
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/normalize_legacy.py`
   - Backfill brand/series:
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/backfill_brand_series.py`
   - Backfill + safe brand cleanup:
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/backfill_brand_series.py --safe-brand-cleanup`
   - Cleanup dry-run:
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/cleanup_legacy_tag_links.py`
   - Cleanup execute (manual-only):
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/cleanup_legacy_tag_links.py --execute`
4. Policy:
   - Cleanup is manual and explicit only.
   - CRM branch backfill is manual-only and starts from dry-run.
   - Tenant-scope backfill execution is retired after the contract migration.
     The retained scripts are report-only unless an expand-schema rollback was
     explicitly reviewed.
   - Shared catalog grants are system-owned. Empty onboarding offers never mean
     share-all, and tenant managers cannot run grant sync or edit inherited
     prices.
   - Tenant manager production provisioning must resolve exactly one healthy
     Patroni primary, use the exact pinned active immutable app container, share
     the `production-release` concurrency group and per-project `.deploy.lock`,
     and accept the password over stdin only. Never add arbitrary SSH commands
     or dynamic secret-name inputs to this workflow.
   - Product media URL repair never widens storefront allowlists and never
     mutates supplier/cost/price data. External sources require an explicit
     rights review and exact host boundary.
   - Post-deploy smoke-check must pass (`/api/health`, `/api/v1/products?limit=5`, `/api/v1/filters/config`) before considering deploy successful.

## Notes

- `docker-compose.yml` service names are `app`, `db`, `web`, `bot` (not `mvn-app`).
- Production API node display names:
  - `mvn-api-nl` is the Netherlands node previously shown as `mvn-api`.
  - `mvn-api-by` is the Belarus node previously shown as `zakup`.
  - These are operator-facing names only. Until a separately reviewed
    infrastructure migration changes them, keep the existing internal Patroni
    member names, SSH aliases, GitHub variables, paths, and compose directories
    (`mvn-api` and `zakup`) unchanged.
- `scripts/normalize_legacy.py` uses shared normalization logic from `services/spec_normalizer.py`; keep both in sync.
- Legacy SQLAdmin was removed; manager app (`manager_frontend/`, Vue) is the internal admin UI.
- Manager list endpoints enforce pagination limits (`limit <= 100`); keep frontend requests within this bound.
