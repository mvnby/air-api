# Storefront catalog revision and cache invalidation

## Boundary

`air-api` owns catalog freshness state. A catalog mutation never calls
Cloudflare from its database transaction. Instead the same caller-owned
transaction:

1. changes the catalog or exact `TenantOffer`;
2. advances the global or storefront revision;
3. inserts one durable outbox event per affected storefront;
4. commits all three effects atomically.

The dedicated catalog worker consumes only
`catalog.cache_invalidation.requested.v1`. The communications dispatcher must
never add this type to its allowlist. Provider I/O happens after the claim
transaction commits and outside every producer transaction.

## Revision contract

The existing global revision remains canonical and numeric. An exact
storefront also has a monotonic local revision keyed by
`(tenant_id, storefront_id)`:

- shared product, brand, series, media or feature changes increment the global
  revision and enqueue one event for every active storefront;
- a real `TenantOffer` change increments only that exact storefront revision;
- an identical offer upsert is a no-op and advances neither revision;
- the public cache key is `g<global>-s<storefront>`.

`GET /api/v1/catalog/revision` remains backward compatible and always returns
HTTP `200`, including when `If-None-Match` matches. Its body is:

```json
{
  "revision": 42,
  "storefront_revision": 7,
  "cache_key": "g42-s7",
  "updated_at": "2026-08-01T12:00:00Z"
}
```

It exposes no internal tenant/storefront IDs. `X-Catalog-Revision` remains the
global numeric value. The response also sets
`X-Storefront-Catalog-Revision`, `ETag: W/"catalog-g42-s7"`,
`Cache-Control: private, no-cache, max-age=0` and
`Vary: X-MVN-Storefront-Host`. A valid signed storefront projection is
stronger: it remains `private, no-store` with `CDN-Cache-Control: no-store`.

## Event contract

One event addresses exactly one storefront and contains only:

- `schema_version=1`;
- `scope` (`global` or `storefront`);
- trusted `tenant_id` and `storefront_id` resolved by the server;
- canonical, sorted `origins` and deterministic, sorted `paths`;
- `global_revision`, `storefront_revision` and matching `cache_key`;
- a bounded machine-readable `reason`.

It contains no secret and no raw request data. An empty `origins` list is the
explicit protocol representation of an active storefront that has no public
domain yet. The worker publishes that event as an observable no-op; it never
falls back to the MVN origin. A routable storefront is required to produce at
least one trusted origin.

## Delivery semantics

Claims use PostgreSQL `clock_timestamp()`, `FOR UPDATE SKIP LOCKED`, a unique
lease token and token-fenced renew/ack/fail transitions. Expired claims return
to delayed retry or become `dead` after their attempt budget. Backoff is
deterministic and exponential.

Delivery is intentionally **at least once**. If Cloudflare accepts a purge and
the worker loses its lease or database acknowledgement, the event is retried
and the same URLs may be purged again. URL purges are idempotent, so this is
safer than acknowledging unconfirmed work. A partial multi-batch failure also
retries the complete event; already successful batches may therefore repeat.
All URLs are retained and sent in Cloudflare-sized batches—there is no
120-URL truncation.

Provider response text is not persisted. Durable errors contain only bounded
exception/error-code classifications.

## Rollout and configuration

Safe defaults keep the worker inert:

```dotenv
CLOUDFLARE_PURGE_ENABLED=false
CLOUDFLARE_PURGE_DRY_RUN=true
CLOUDFLARE_ZONE_ID=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_PURGE_ZONE_HOSTNAMES=mvn.by
CATALOG_INVALIDATION_WORKER_ENABLED=false
CATALOG_INVALIDATION_WORKER_POLL_SECONDS=2
CATALOG_INVALIDATION_WORKER_LEASE_SECONDS=120
CATALOG_INVALIDATION_WORKER_RECOVERY_LIMIT=100
```

Deploy in this order:

1. apply the additive migration while the worker is disabled;
2. deploy producers and verify pending exact-type events/revisions;
3. verify the token is purge-only, the zone ID is correct and
   `CLOUDFLARE_PURGE_ZONE_HOSTNAMES` covers every active event origin;
4. set Cloudflare to enabled, non-dry-run live mode;
5. enable the catalog worker only on the single-active primary scheduler;
6. canary one catalog change, then one `TenantOffer` change, and verify the
   outbox reaches `published` and the public cache key advances as expected.

The worker performs its provider preflight before claiming. `disabled`,
`dry_run`, `missing_config` and malformed `invalid_config` modes leave events
pending and consume zero attempts.
An origin outside the configured zone is terminal after one classified
attempt, rather than burning the full retry budget against the wrong zone.

The current runtime supports one Cloudflare zone/token. A white-label custom
domain in another Cloudflare zone is blocked from this worker and requires
explicit per-zone credential routing before activation. Do not widen one token
to unrelated zones as a shortcut.

## Monitoring and rollback

Monitor only the exact event type:

```sql
SELECT status, count(*)
FROM integration_outbox_event
WHERE event_type = 'catalog.cache_invalidation.requested.v1'
GROUP BY status;
```

Alert on growing `pending`, any persistent `processing` beyond the lease, and
new `dead` rows. During rollback, disable the worker first and wait until no
catalog events are `processing`. Do not downgrade the revision table while new
producers are running. Pending events may be retained for a corrected rollout;
review them before re-enabling so stale work is not mistaken for a fresh
canary.
