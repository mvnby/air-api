# Tenant and storefront onboarding

`scripts/manage_storefront_onboarding.py` is the single lifecycle implementation
for reviewed tenant/storefront provisioning. It accepts a closed JSON manifest,
never creates credentials, and never deletes tenant data.

The manifest owns exact tenant/storefront identity, an exact hostname allowlist,
and at most 100 reviewed offers. Unknown fields, credential-shaped fields,
reserved MVN hostnames, ports, URLs, and hostnames outside the manifest allowlist
fail closed. A managed tenant must be a non-system `independent_seller`; the
legacy Orsha canary is a thin adapter for an existing system tenant.

## Transaction contract

Planning is read-only. Every mutation requires a signed plan token that expires
after 15 minutes. Execution takes transaction-scoped advisory locks for the
tenant/storefront and hostname, then locks persisted rows in deterministic order,
rebuilds the plan, and rejects stale state or a changed manifest.

Services and CRUD only stage writes. The CLI alone commits or rolls back. Tenant,
storefront, domain, offer, audit, catalog revision, and catalog invalidation
outbox changes therefore share one database transaction. Disable preserves all
rows and CRM history.

## Polotsk sequence (not executed by this change)

The reviewed manifest is
`config/storefront_onboarding/polotsk.json`. It intentionally starts with an empty
offer set; add reviewed public product offers to that same bounded file before
bootstrap if the storefront must launch with catalog inventory.

Run each plan immediately before its matching mutation and copy only the emitted
`reviewed_execute_command` after reviewing `blockers`, `changes`, resolved offers,
and the manifest fingerprint:

```bash
python3 scripts/manage_storefront_onboarding.py plan \
  --for-action bootstrap \
  --manifest config/storefront_onboarding/polotsk.json \
  --hostname polotsk.mvn.by
```

After bootstrap commits, provision DNS/TLS outside this CLI and independently
prove that `polotsk.mvn.by` reaches the intended storefront gateway. Then plan
and execute domain verification:

```bash
python3 scripts/manage_storefront_onboarding.py plan \
  --for-action verify-domain \
  --manifest config/storefront_onboarding/polotsk.json \
  --hostname polotsk.mvn.by
```

Only after the DNS/TLS proof and `verify-domain` commit should activation be
planned and executed:

```bash
python3 scripts/manage_storefront_onboarding.py plan \
  --for-action activate \
  --manifest config/storefront_onboarding/polotsk.json \
  --hostname polotsk.mvn.by
```

Activation atomically changes routability, writes audit events, bumps the
storefront catalog revision, and enqueues the catalog invalidation outbox event.
Verify public context resolution and catalog isolation after the outbox event is
published.

Emergency disable is the same two-step plan/execute flow with
`--for-action disable`. For a managed tenant it disables the tenant, storefront,
domain, and every offer without deleting CRM or catalog rows, and atomically
stages a final catalog invalidation while the route is still observable.
