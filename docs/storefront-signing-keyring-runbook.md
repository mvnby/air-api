# Storefront signing keyring: HA activation and rotation

## Safety boundary

The API keyring is an infrastructure credential shared only with a trusted
storefront server runtime. It is not a browser key, tenant login credential or
database setting. Never put the JSON, a secret, or a secret-derived diagnostic
value into Git, GitHub Actions inputs/artifacts, issue text, shell tracing,
application logs or chat.

Production currently has two Patroni API nodes. The Netherlands node reads
`/opt/air-api/.env`; the reserve node reads the file selected by
`MVN_RESERVE_ENV_FILE` (normally `/opt/mvn-reserve/.env`). Both active and
fenced API containers must receive the same keyring before a storefront is
allowed to depend on failover.

## Closed JSON format

`STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON` is a single-line JSON object:

```json
{"keys":{"polotsk-web-2026-08":{"secret":"<32+ random bytes>","host_roles":{"polotsk.mvn.by":"primary"}}}}
```

Only `keys`, `secret`, `host_roles`, exact canonical hostnames, and the roles
`primary`/`previous` are accepted. Each key has exactly one host role. There is
no wildcard, suffix, alias sharing, inherited or database-driven authorization.
Generate a dedicated high-entropy secret for every hostname; secrets must also
be unique across key IDs. Never reuse `SECRET_KEY`, bot, Cloudflare or database
credentials.

## Mandatory preflight before the first keyring-aware image

If production still uses the historical primary/previous variables, first add
this ignored-by-old-code setting to **both** node env files:

```text
STOREFRONT_CONTEXT_LEGACY_ALLOWED_HOSTS=mvn.by
```

Confirm `PUBLIC_SITE_URL=https://mvn.by` on both nodes. Do this before deploying
the keyring-aware image: the new image deliberately refuses a global legacy
key without this exact canonical binding. Do not add Polotsk to the legacy
allowlist; startup validation rejects it.

## Add Polotsk without changing canonical MVN signing

1. Generate the Polotsk secret in an approved password/secret manager. Build
   the one-line JSON locally without shell tracing and keep the env files mode
   `0600`.
2. Add the same `STOREFRONT_CONTEXT_SIGNING_KEYRING_JSON` value to both API node
   env files. The existing bounded legacy MVN key may remain during this step
   because the host bindings do not overlap.
3. Validate the value offline with the candidate image. The safe inventory
   prints only public key IDs, roles and hostnames:

   ```sh
   docker compose exec -T app python3 scripts/validate_storefront_signing_keyring.py
   ```

   Expected inventory includes exactly one Polotsk `primary` and no unexpected
   hostname. Treat any startup/validation error as a stop condition.
4. Restart/deploy the fenced replica first. Confirm its container is healthy,
   remains fenced for public traffic, and prints the same safe inventory.
5. Restart/deploy the active node. Confirm `/api/health` and the existing MVN
   catalog smoke checks before changing the storefront runtime.
6. Configure the trusted Polotsk server runtime with only its key ID/secret and
   exact `polotsk.mvn.by` public host. Run signed read and idempotent Lead/Order
   canaries. A deliberate request claiming `mvn.by` with the Polotsk key must
   return `401`.
7. Exercise the documented HA node path or controlled failover canary. Do not
   activate DNS/customer traffic until both nodes accept the legitimate
   Polotsk envelope and reject the cross-host envelope.

## Rotate one host without downtime

For the host being rotated, publish two entries in the API JSON: the new key is
`primary`, the old key is `previous`. No other host changes role.

1. Install the identical two-key configuration on both API nodes, replica
   first, then active; validate the safe inventory after each restart.
2. Switch the storefront runtime to the new primary and run read/write
   idempotency canaries.
3. Wait longer than `STOREFRONT_CONTEXT_MAX_AGE_SECONDS` after the last request
   signed by the old runtime.
4. Remove the previous entry from both nodes, replica first. Repeat canaries.

To migrate canonical MVN completely off the historical variables in one
release, place the existing key in JSON as `previous`, the new key as `primary`,
and remove all four historical pair variables plus the legacy-host setting in
the same node-local env edit. The old runtime remains accepted until it is
switched and the age window has elapsed.

## Rollback

- Before a runtime switch: restore the previous node env file and restart the
  affected candidate/container. No DNS or database rollback is needed.
- After a runtime switch but within the age window: keep both bindings and
  switch the storefront runtime back to the old key; do not label two keys
  `primary`.
- If only one API node has the intended inventory, keep storefront activation
  blocked. Restore identical configuration before any failover test.
- A key suspected of disclosure is not a normal rollback: replace it, keep the
  signing window short, inspect request logs for key IDs/hosts only, and revoke
  the compromised binding as soon as the new runtime is live.

The validation command intentionally cannot prove that two secret values are
equal because it never emits secret hashes. Equality is established by secure
configuration management plus successful signed canaries against both nodes.
