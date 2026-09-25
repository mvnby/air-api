# Partner site settings and service catalog

`/manager/settings` is the tenant owner's setup page: company requisites for
documents, public site contacts, enabled service directions and the team link.
Platform configuration remains under `/manager/settings/platform` with
infrastructure permissions. Public email is a contact address; saving it does
not configure an inbox or notification delivery.

## Data boundaries

- Settings belong to one trusted tenant/storefront pair. The request body cannot
  select another tenant. Updates use a version and emit an audit event.
- The site's `display_name`, full `logo_asset_id` and optional
  `compact_logo_asset_id` in `storefront_settings` are the canonical brand for
  that storefront. Manager owners upload images through
  `POST /api/manager/storefront-settings/logo`, which uses the existing media
  library processing/storage path and scopes the resulting asset to the current
  tenant/storefront. Settings updates reject assets from another scope.
  `GET /api/manager/storefront-settings/brand` gives authorized owners and
  managers the same name and resolved URLs used by the public
  `GET /api/v1/storefront-settings`. The public site's trusted runtime should
  consume `site.display_name`, `site.logo_url` and
  `site.compact_logo_url` from that response and render SVG only through `img`.
  A missing or failed image falls back to the name and initials.
- Partner defaults contain no canonical phone/email or enabled services.
  Canonical defaults retain existing public contacts and five enabled directions.
- Installation, pre-installation, dismantling, maintenance and repair can be
  switched independently. Public tariff reads and calculations reject disabled
  directions and foreign tariff IDs. Preview calculations do not save estimates.
- The start template makes detached copies of service options, CRM tariffs and
  rules, and public installation rates. These remain separate pricing contracts.
  When the canonical installation draft matches its latest approved book, the
  same initial transaction publishes a tenant-owned book from the detached
  installation copy. Pending canonical edits block the copy instead of
  seeding an unapproved price.
  Copying never imports customers, orders, requisites, permissions or discounts.
  Existing partner data is never overwritten. Managers edit their tenant's prices.
  The separately authorized [installation grid rollout](installation-grid-rollout.md)
  is a one-time reviewed reset of installation drafts only; it retains prior
  rows and publishes tenant-owned books. Ordinary onboarding never repeats it.
- Canonical legacy rows retain nullable ownership during this additive migration;
  only canonical scope may read them. All new partner rows have explicit ownership.

## Initial preview setup

Apply migrations and deploy the same reviewed image to **both API nodes before
creating any partner service rows**. An old image without tenant filters must not
run after copying data. Keep the prior preview disabled until this is verified.

Use [production data operations](production-data-operations.md) and
[storefront onboarding](storefront-onboarding.md) for a new tenant/domain.
`config/storefront_onboarding/test1.json` bootstraps a separate Test 1 tenant;
`config/shared_catalog_grants/test1.json` explicitly grants published products.
Empty onboarding offers do not grant products implicitly.

On the exact immutable active primary container, run:

```sh
python3 scripts/manage_partner_site_setup.py plan --manifest config/partner_site_setup/test1.json
python3 scripts/manage_partner_site_setup.py plan --manifest config/partner_site_setup/polotsk.json
```

Review the exact target IDs, contact values, enabled directions, source counts,
fingerprint and empty blockers. Run only the fresh plan's emitted
`reviewed_execute_command` within 15 minutes. Each command atomically initializes
settings and copies prices. Any initialized target is blocked; subsequent edits
belong in Manager. No staff account is created or promoted by this operation.

Test 1 starts with blank contacts; Polotsk keeps its own public name and phone.
The preview host has HTTP Basic Auth `123` / `123`, `noindex, nofollow, noarchive`,
no public sitemap and no order/lead writes. This credential is only a preview
indexing barrier, never a Manager or service-signing credential.

Configure each exact hostname with its own signing key following the
[signing keyring runbook](storefront-signing-keyring-runbook.md). Both API nodes
must accept the legitimate host and reject a signature claiming another host
before DNS/customer traffic is activated.

Verify the ordinary API smoke checks, anonymous preview 401, authenticated 200,
robots headers, enabled service pages and nonpersisting calculations. A disabled
direction and a tariff ID from another tenant must fail without exposing prices.

## Rollback

Before initial copying, the additive schema can remain while application code
rolls back. After partner rows exist, never roll back to an unscoped application
image: it could mix partner and canonical catalogs. Disable the affected preview
and ship a forward fix or a rollback image retaining tenant filters. Deleting
partner rows requires a separately reviewed data operation; no automatic cleanup.

## Employee bot direction

The current staff bot contract remains system-tenant scoped. The intended next
step is one shared staff bot with single-use tenant-bound invitations, active
membership checks on every action, and role-specific access (manager vs assigned
executor). A branded separate bot can later use the same tenant-aware contract.
Changing a public Telegram support link does not grant staff access. Do not point
partners at the current staff bot as if tenant invitations were already supported.
