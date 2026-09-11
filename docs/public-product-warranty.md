# Public product warranty contract

Public product payloads expose the selected general equipment warranty as
`warranty`. The field is present on full products, search results and series
siblings. It is `null` when no public rule applies.

```json
{
  "duration_months": 84,
  "maintenance_required": true,
  "maintenance_interval_months": 12,
  "start_event": "installation",
  "allowed_maintenance_provider": "mvn",
  "grace_period_days": 30,
  "terms": "Annual maintenance is required."
}
```

`start_event` is one of `sale`, `installation`, `commissioning` or `manual`.
`allowed_maintenance_provider` is one of `any`, `mvn` or `authorized`.

Only active `supplier` coverage policies with `supplier_id IS NULL` are public.
The existing resolver selects product before series, series before brand and
brand before an existing global rule. Within the same scope the newest
`created_at` and then the greatest ID win. Effective date boundaries are
inclusive. Supplier-specific, `mvn_work` and `legacy` policies never participate.

The API evaluates effective dates at request time. Warranty policy writes also
advance the global catalog revision and stage cache invalidation in the same
transaction. Storefront runtime caches must revalidate this time-dependent
projection within 30 seconds so an effective-date boundary does not depend on a
later policy write. Signed storefront API responses remain `private, no-store`.

The public object intentionally excludes policy IDs and names, supplier data,
procurement data, internal coverage decisions and coverage snapshots. Legacy
`specs.warranty_months` is not a fallback because historical bare values mix
months and years. A storefront may apply its own documented presentation
default when `warranty` is `null`.
