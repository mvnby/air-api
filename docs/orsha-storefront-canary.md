# Internal Orsha storefront canary

This runbook manages one bounded second storefront for the existing system
tenant `mvn`. It does **not** create a tenant, membership, external customer, or
public route. The fixed storefront identity is `mvn/orsha`; only a reviewed
`orsha*.mvn.by` hostname and 5–20 explicitly selected products are accepted.

The command is dry-run by default. Bootstrap, activation, and disable are three
separate review-token guarded transactions. Bootstrap stops at `draft` plus a
`pending` primary domain. It never activates public traffic.

## Release prerequisites

Do not operate this canary until the deployed release contains all of the
following:

1. trusted signed storefront context at the API boundary;
2. storefront-scoped public offers with deny-by-default visibility;
3. storefront catalog revision plus durable purge outbox;
4. the lifecycle command and its PostgreSQL integration tests;
5. a routing change window with one named operator.

The offer staging helper owns no commit. Each lifecycle action and its
`TenantAuditEvent` rows share one caller-owned transaction. Routable activation
and disable also require catalog revision/outbox staging in that same
transaction; the plan fails closed when that release boundary is unavailable.
When rebasing this branch onto the catalog revision release, retain
`TenantOfferCatalogInvalidationAdapter` and remove any duplicate direct
invalidation call from `TenantOfferService`.

## Reviewed offer manifest

Use only known globally published products. Prices and publication decisions
are exact; the command does not infer them from the shared `Product` row. The
example contains fictional slugs and must not be copied to production without
review:

```json
{
  "version": 1,
  "offers": [
    {"product_slug": "reviewed-model-a", "price": 2200, "old_price": 2400, "is_published": true},
    {"product_slug": "reviewed-model-b", "price": 2500, "old_price": null, "is_published": true},
    {"product_slug": "reviewed-model-c", "price": 2800, "old_price": 3000, "is_published": true},
    {"product_slug": "reviewed-model-d", "price": 3100, "old_price": null, "is_published": false},
    {"product_slug": "reviewed-model-e", "price": 3400, "old_price": 3600, "is_published": false}
  ]
}
```

The file is limited to 64 KiB and has a closed schema. A product can instead be
selected by `product_id`, but production IDs must come from a fresh database
report and must not be committed to this repository. Repeated CLI arguments are
also supported:

```bash
--offer-slug reviewed-model-a 2200 2400 true
--offer-id 123 2500 - false
```

## Bootstrap without traffic

Run the command inside the released API image. Replace the hostname and file
path with reviewed values:

```bash
python3 scripts/manage_orsha_storefront.py \
  --hostname orsha-internal.mvn.by \
  --offers-file /run/operator/orsha-offers.json
```

The report must say `ready: true`. Review every resolved product, price,
publication flag, ownership field, blocker, and proposed change. Copy the
printed `reviewed_execute_command` exactly. It includes a signed plan token that
expires after 15 minutes. Any relevant database or manifest change makes that
token stale and execution fails closed.

After execution, check status:

```bash
python3 scripts/manage_orsha_storefront.py \
  --status \
  --hostname orsha-internal.mvn.by
```

Expected state: tenant `mvn`, storefront `orsha/draft`, exactly one
`pending`/primary domain, and exactly the reviewed offers. A repeated fresh
bootstrap plan must contain no changes; executing that no-op must add no audit
rows.

## Domain verification and explicit activation

After the reviewed DNS/TLS target has been independently proved, plan domain
verification without the offer file:

```bash
python3 scripts/manage_orsha_storefront.py \
  --plan-for verify-domain \
  --hostname orsha-internal.mvn.by
```

Run the printed `--verify-domain` command. This records the verification audit
timestamp but keeps the domain pending and the storefront draft.

Activation requires the same exact manifest. First review:

```bash
python3 scripts/manage_orsha_storefront.py \
  --plan-for activate \
  --hostname orsha-internal.mvn.by \
  --offers-file /run/operator/orsha-offers.json
```

Then run the printed command, which uses `--activate` and the fresh token. The
transaction activates the already verified storefront and domain, appends audit
rows, and stages one storefront catalog invalidation batch. It does not
configure DNS, Cloudflare, TLS, or a storefront deployment.

Before routing real traffic, verify:

1. signed `GET /api/v1/storefront/context` resolves `mvn/orsha` and the reviewed
   hostname, city, locale, and currency;
2. the public catalog exposes only active, published allowlisted offers at the
   exact reviewed prices;
3. forged or missing context is rejected and creates no Lead or Order;
4. one synthetic Lead and Order persist with the Orsha storefront scope and are
   visible only in the selected Manager context;
5. the catalog revision/outbox event is delivered and cache purge succeeds;
6. canonical `mvn/main` health, catalog, checkout, and Manager flows remain
   healthy.

## Disable and rollback

Disable deliberately accepts no offer manifest, so an emergency rollback does
not depend on a mutable file. A fresh plan shows every affected row:

```bash
python3 scripts/manage_orsha_storefront.py \
  --plan-for disable \
  --hostname orsha-internal.mvn.by
```

Run the printed `--disable` command. New CRM traffic is excluded from the plan
token, so a Lead arriving between plan and execute cannot prevent rollback.
The transaction stages cache invalidation while the route is still resolvable,
then disables every Orsha offer, the domain, and the storefront.

Disable performs no hard delete. Products, `Customer`, `Lead`, `Order`, and all
append-only audit history remain intact. DNS/proxy withdrawal is a separate
infrastructure action and should follow successful API disable. Verify status,
public denial for Orsha, and continued canonical `mvn/main` health.

## Fail-closed conditions

Stop and investigate instead of editing rows manually when the report shows:

- missing, disabled, or non-system tenant `mvn`;
- unexpected Orsha ownership metadata;
- hostname owned by another storefront or a different stored hostname;
- multiple, non-primary, or otherwise unexpected stored domains;
- missing/unpublished products, duplicate references, more than 20 offers, or
  stored offers outside the reviewed allowlist;
- stale plan token or an occupied PostgreSQL advisory lock;
- unavailable catalog invalidation staging for a routable lifecycle change;
- failed post-condition or audit/revision/outbox write.

The caller rolls the whole mutation back on every error. Never bypass the plan
token, change ownership fields in production, hard-delete canary rows, or retry
with an old manifest.
