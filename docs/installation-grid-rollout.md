# Installation grid: reviewed draft reset and publication

The initial owner-approved grid was published on September 25, 2026 for the
canonical company, Polotsk, and Test1. See the [dated release record](installation-grid-release-2026-09-25.md).
This runbook describes the guarded procedure; the signed initial plan has
already been applied and must not be reused. A correction needs a fresh plan
and a new immutable book revision.

The owner-approved September 25 grid is defined once in
`services/installation_grid_seed.py`. This procedure replaces **active
installation drafts** for the canonical tenant and every explicitly listed
active partner, then publishes a new immutable book for each tenant in one
database transaction. It never deletes old tariff/rule rows or edits published
books, estimates, orders, or documents. Non-installation tariffs and disabled
tenants stay unchanged. Partner drafts copied by the initial setup remain
detached and independently editable after this one-time reset.

After the canonical book is published, new-partner initial setup copies only
active canonical installation drafts and publishes a new tenant-owned initial
book in the same transaction. It refuses to clone if the canonical draft has
unpublished edits relative to the latest approved book. Existing partners are
never synchronized on ordinary edits or onboarding calls.
Legacy installation rates and installation service/option rows are excluded
from that new-partner copy once the book exists; non-installation catalog rows
remain in the template. A canonical tariff rule referencing an excluded
service blocks onboarding until the reference is corrected.

Read [production data operations](production-data-operations.md) and
[deployment](deployment.md) first. Use the exact immutable app image on the
healthy Patroni primary, under the production deploy lock; do not run this
command on a replica or from a local checkout. Production apply belongs to the
release coordinator after review of the plan and deployed read-path evidence.

## Read-only inventory and plan

Start with a read-only discovery plan, without readiness claims:

```sh
python3 scripts/manage_installation_grid_rollout.py plan
```

It reports every active partner slug and tenant/storefront ID, the canonical
scope, demo flags, disabled tenants excluded from mutation, every old
installation draft/rule price, currently published book prices, legacy public
rates/options, and the exact new grid. `old_to_new` and each legacy rate's
`price_comparison` show the old and candidate new amount, included route, and
extra-meter price. `unmapped_or_ambiguous_requires_review` is deliberate: the
legacy selector checks area tags before capacity, and its 18/24 or 30/36 bands
can cross the approved 8.0 or 10.55 kW boundary. A candidate is not proof of
equivalent matching. Do not hide such rows or claim the old calculator already
uses the new price.

Before requesting an executable plan, verify all of these on the actually
deployed revisions:

- The public web v2 installation path uses the published book for exact
  resolve/preview/accepted checkout and treats unsupported multi/prelaid
  product checkout as a quote. Record its full commit and a runtime smoke URL.
- Verify the active backend source SHA and immutable image digest on both API
  and both worker runtimes. Bind that reviewed SHA and digest into the plan;
  a CI or PR URL alone is not runtime evidence.
- Legacy `with_installation`/`InstallationPricingService` requests cannot create
  a fixed order from stale `InstallationRate` data once a book is published.
  Record a test or runtime evidence URL.
- The public `/api/v1/installation-rates`, `/api/v1/services/options`, and
  `/api/v1/content/services` lists must not expose stale installation prices
  as a second current source after web v2. One evidence URL may cover all
  three installation-list guards; retain underlying rows for history and keep
  non-installation services visible.
- The old `/api/v1/service-pricing/calculate` path cannot calculate installation
  from active typed drafts without the shared-hole, multi-unit, and provisional
  access rules. Require an installation-only fail-closed guard and record its
  evidence URL; other service directions retain their existing calculator.
- The Manager `/installation-rates` editor is read-only or clearly retired
  after publication. The old `/api/manager/service-estimates/calculate` and
  `/api/manager/service-estimates` write paths, plus the order's quick service
  picker, cannot calculate or add installation from base prices without the
  shared-hole, multi-unit, and provisional rules. Historical estimate reads
  and existing order lines remain available. Cover all of these Manager guards
  with the same `--manager-editor-proof` evidence URL. The typed tariff editor
  remains the draft source for later tenant-specific edits.
- Review the exact active partner list and demo flags. Include each active
  partner with `--expected-partner`; no implicit share-all or partial subset.
  Add `--include-demo-reset` only if the report shows a demo tenant that the
  owner authorized for this reset. This flag affects this operator command
  only; it does not weaken Manager's demo write guard.
- Inspect every old/new price and coverage row, especially ceiling, duct,
  multisplit, pump, shared hole, and prelaid work. The seed has no unapproved
  discount and no fixed prelaid new-route price. Only standard wall large from
  8.0 through observed 10.55 kW is fixed; above that remains quote.

Run a new plan with the exact partner slugs, full web commit, and direct
evidence URLs. For example, substitute the *reported* slugs and reviewed
URLs rather than copying these placeholders:

```sh
python3 scripts/manage_installation_grid_rollout.py plan \
  --expected-partner PARTNER_SLUG \
  --backend-release-commit EXACT_BACKEND_40_CHARACTER_SHA \
  --backend-image-digest sha256:EXACT_BACKEND_64_HEX_DIGEST \
  --web-v2-commit EXACT_40_CHARACTER_SHA \
  --web-v2-proof https://example.invalid/web-runtime-evidence \
  --manager-editor-proof https://example.invalid/manager-guard-evidence \
  --legacy-list-proof https://example.invalid/old-installation-list-guards \
  --legacy-calculate-proof https://example.invalid/legacy-guard-evidence \
  --legacy-tariff-calculate-proof https://example.invalid/old-tariff-guard-evidence
```

The plan is ready only with zero blockers. Store its full report in a
restricted operator artifact, not a public issue: it includes tenant pricing
and a signed 15-minute token. Review `plan_digest`, `seed_digest`, every
scope ID and `old_to_new`/`legacy_public_rates` row. Run **only** the emitted
`reviewed_apply_command` on the same primary and active image before expiry.
Do not hand-edit its arguments or reuse a token after data or code changes.

## Apply and verification

The command runs in a serializable transaction. It locks active tenant rows,
their default storefronts, and installation draft/rule rows in a stable order;
legacy rates, options, latest books and service settings are read into the
fresh full-state digest without row locks. It compares that digest and the
exact expected partner set with the signed
plan. Any change or blocker aborts before mutation. In the one transaction it
marks old installation drafts inactive, inserts the approved canonical grid,
inserts detached partner copies with source links, publishes a new immutable
book per scope, and writes an audit record with each complete old draft/rule
pre-image. Failure rolls the whole transaction back; a successful result lists
each new book ID, revision and fingerprint. Existing inactive rows remain as
a second local backup of the prior drafts.

After apply, verify the new book fingerprints and revisions for *every* listed
tenant; check the public exact-price and quote cases through the approved web
path and the four standard API smoke endpoints. Recheck Manager's legacy
editor guard and old checkout fail-closed behavior. A book revision is not
evidence that web traffic used it until those runtime checks pass.

If a post-commit correction is needed, do not delete or rewrite a book or an
accepted quote. Keep the site on its safe read path, prepare a new reviewed
plan using the retained inactive rows/audit pre-image, and publish a **new**
revision with the restored draft prices. Old accepted revisions remain valid.
Rollback of application code must retain tenant-scoped book reads and the
legacy-input guard; rolling back to an unscoped or stale-price checkout image
after publication is unsafe.
