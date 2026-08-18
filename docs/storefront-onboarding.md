# Tenant and storefront onboarding

`scripts/manage_storefront_onboarding.py` is the single lifecycle implementation
for reviewed tenant/storefront provisioning. It accepts a closed JSON manifest,
never creates credentials, and never deletes tenant data.

The manifest owns exact tenant/storefront identity, an exact hostname allowlist,
and at most 100 reviewed launch/canary offer exceptions. Empty `offers` means
that the storefront receives no offers; it never means "share all products".
Unknown fields, credential-shaped fields, reserved MVN hostnames, ports, URLs,
and hostnames outside the manifest allowlist fail closed. A managed tenant must
be a non-system `independent_seller`; the legacy Orsha canary is a thin adapter
for an existing system tenant.

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
offer set, so bootstrap alone exposes no catalog inventory. The bounded manifest
may carry a small, explicitly reviewed launch/canary subset, but it is not a bulk
catalog transport. Full Polotsk inventory from the shared master catalog requires
a separate system-owned catalog grant/sync boundary, with its own review and
tests, before activation or any catalog presentation. That capability is not
implemented by this onboarding change.

Run each plan immediately before its matching mutation and copy only the emitted
`reviewed_execute_command` after reviewing `blockers`, `changes`, resolved offers,
and the manifest fingerprint:

```bash
python3 scripts/manage_storefront_onboarding.py plan \
  --for-action bootstrap \
  --manifest config/storefront_onboarding/polotsk.json \
  --hostname polotsk.mvn.by
```

After bootstrap commits, establish and verify the separately implemented
system-owned catalog grant/sync if Polotsk must present full shared inventory.
Do not substitute more than 100 manually copied manifest offers for that
boundary. Provision DNS/TLS outside this CLI and independently prove that
`polotsk.mvn.by` reaches the intended storefront gateway. Then plan and execute
domain verification:

```bash
python3 scripts/manage_storefront_onboarding.py plan \
  --for-action verify-domain \
  --manifest config/storefront_onboarding/polotsk.json \
  --hostname polotsk.mvn.by
```

Only after the DNS/TLS proof, `verify-domain` commit, and any required full-catalog
grant/sync verification should activation be planned and executed:

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
