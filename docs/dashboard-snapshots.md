# Manager dashboard freshness

`GET /api/manager/dashboard/overview` recalculates canonical CRM sales, payments,
receivables, stage events and comparisons from the current authenticated
storefront. It reads external analytics only from PostgreSQL snapshots; it never
calls a provider, schedules a task or waits for a refresh. Legacy `/stats` remains
an operational summary with different sales definitions. Personal unread counts
remain a separate authorized request. Bank receipt review remains system-only.

## Source snapshots

Each record identifies tenant, storefront, source, stable connection/configuration
revision, exact start/end dates (end exclusive), and calculation schema version.
The revision includes the public property/host configuration and connection
identity. A manual credential replacement changes it; OAuth access-token refresh
does not. Disabling/removing a connection immediately removes it from reads.
Legacy environment Metrika credentials apply only to a system tenant with an
explicit matching storefront counter.

A source retains its last successful payload separately from its last attempt,
error code and next retry. A failed source cannot erase another source's success.
During a day boundary the reader may use an earlier end date for the same month
start and connection revision, with the actual dates and stale status. A new
month/configuration never borrows another month's/configuration's data. Missing
configured sources are `pending`; failed first attempts have no invented zeros.

The existing HA-fenced scheduler runs discovery every 60 seconds, including at
startup. It refreshes traffic/advertising about hourly and SEO every three hours.
It owns separate sessions, runs at most two sources concurrently and attempts at
most 24 keys per pass, oldest attempts first. Current and comparable previous
marketing periods are separate keys; SEO refreshes the current period.

Claims are short PostgreSQL atomic leases committed before provider I/O. Each
completion is fenced by its lease token. The per-source deadline includes OAuth;
cancelled workers stop with the scheduler and their leases expire after 90
seconds. Retry delays grow from one minute to one hour. No request visitor can
start a refresh storm. A missing scheduler owner leaves saved data readable and
new sources visibly pending. Use the existing [HA runtime procedure](api-ha-runbook.md)
to diagnose ownership rather than running a second worker manually.

## Frontend lifecycle

The home retains only one in-memory user/company/storefront/permission context.
Navigation back shows the retained result while revalidating. Context changes,
logout and auth recovery clear it, including while the home is unmounted. Live
CRM/operational reads refresh on entry, focus, relevant inbox changes and every
45 seconds while the page is visible, without overlapping a resource's requests.
Refresh errors leave the previous result visible and disclose its timestamp.
Each external source shows its own period and last successful update.

## Rollout and rollback

Apply migration `dash20261023snap01` before starting the new application image.
It adds the cache table and a defaulted connection revision; it changes no CRM,
orders, payments or business documents. Existing active connections are discovered
automatically; no backfill or provisioning command is required. First launch can
show pending analytics until the scheduler finishes its first bounded passes.

Verify normal [deployment smoke checks](deployment.md), then authenticated home
CRM latency, source timestamps/states, and scheduler ownership. Do not create
production test sales. Provider failures are a partial analytics state, not a
reason to block the home page.

For application rollback restore the previous image and leave the additive
migration in place. It safely ignores the cache and revision column. Only after
all new application workers have stopped may a separately reviewed downgrade
remove the table/column; it discards cached analytics only. Do not downgrade under
running new workers. The previous application resumes its former synchronous
provider behavior.
