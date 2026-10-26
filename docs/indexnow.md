# IndexNow catalog notifications

The canonical MVN storefront can notify Yandex automatically when committed
catalog mutations change public product or brand URLs. Web article and page
releases are handled separately by `mvnby/mvn-web`, after public deployment
smoke checks. Google Indexing API is not used: ordinary product and article
pages are outside its supported job/live-video scope.

## Delivery boundary

`INDEXNOW_ENABLED=false` is the default. When enabled, the existing catalog
producer stages `search.indexnow.requested.v1` in the same transaction as the
catalog mutation and cache invalidation. Only the system default storefront
with the exact `https://mvn.by` origin qualifies. Partner domains, preview
hosts, query URLs, checkout and arbitrary additional purge paths are excluded.
Only explicit affected catalog paths are sent; there is no historical dump.
A shared producer-side DAO checks current publication before staging product,
brand or series URLs. Products require publication; brands also require at least
one published product; series require a published series and brand, matching the
canonical series endpoint (which also serves empty published series). Public
catalog and brand listing URLs remain eligible. New or repeatedly edited drafts
are excluded.

Rename, unpublish and delete producers explicitly snapshot public paths before
the mutation and pass this evidence in the same transaction. This retains old
public product, brand and series URLs without treating a missing database row or
current 404 as evidence of prior publication. Product bulk publication reuses
the same product writer; MDV replacement preserves snapshots for both archive
and staged deletion. A renamed product retains both its old and new URL in the
invalidation.

The independent HA-fenced scheduler worker cannot claim the notification until
its exact parent cache invalidation is `published`. A failed or disabled purge
therefore leaves the child pending without consuming attempts. IndexNow
delivery cannot alter or block the completed purge. The communications worker
does not consume these events.

The worker fetches the public ownership key from
`https://mvn.by/indexnow-key.txt`, validates its format without following
redirects, and posts canonical URLs to `https://yandex.com/indexnow`. No OAuth,
provider credential, migration or additional database is needed. Provider requests
identify themselves as `MVN-IndexNow/1.0 (+https://mvn.by/)`. The key is
public by design. Notifications are split at the 10,000 URL protocol limit.

Claims reuse the catalog worker's DB-clock lease and token-fenced transitions
with a separate event type. Network I/O runs outside database transactions,
with a 45-second operation timeout and a 120-second lease. Expired work is
recoverable. Delivery is at least once: a crash after provider acceptance can
produce a safe duplicate on retry. Transient HTTP errors use persisted
exponential backoff, up to 24 attempts; invalid requests (400/422) become
`dead` for review. Provider response text is not persisted.

HTTP 200 and 202 mean **notification accepted**, not indexed. In particular,
202 may still be waiting for ownership verification. Search inclusion remains
subject to the search engine, canonical URLs and robots directives.

## Rollout and rollback

1. Deploy the web ownership files first and verify the stable key URL returns
   HTTP 200 and the expected 8–128 character public key.
2. Confirm live catalog purge configuration and its worker are healthy. Inspect
   both API hosts read-only; preserve the HA role and scheduler fence.
3. Add `INDEXNOW_ENABLED=true` to both API runtime environment files under the
   deployment lock, then release the tested API image through the normal
   [deployment procedure](deployment.md). Existing containers retain their old
   configuration until replacement. Only future mutations on the enabled
   producer create notifications; enabling does not scan old outbox events.
4. Check health/products/filters, active scheduler stability, the enabled flag,
   and the queue after the next genuine catalog edit. Do not change a business
   price solely to generate a test notification.

To pause, set `INDEXNOW_ENABLED=false` and redeploy through the same procedure.
Pending rows are preserved. To roll back code, use the previous immutable API
image; catalog data and cache events remain valid. Never delete queue rows as
a retry mechanism.

Read-only queue report:

```sql
SELECT status, count(*) AS events, min(available_at) AS oldest_due,
       max(published_at) AS last_accepted
FROM integration_outbox_event
WHERE event_type = 'search.indexnow.requested.v1'
GROUP BY status;
```

Inspect pending children together with their `payload.catalog_event_id` parent
before treating a delivery delay as a provider failure. A `dead` child or parent
needs diagnosis; existing production data-operation review gates apply to
manual queue repair. The log distinguishes acceptance from indexing and shows
the response status and number of submitted URLs.

Sources: [Yandex IndexNow](https://yandex.ru/support/webmaster/ru/indexing-options/index-now),
[protocol](https://www.indexnow.org/documentation),
[Google Indexing API scope](https://developers.google.com/search/apis/indexing-api/v3/using-api).
